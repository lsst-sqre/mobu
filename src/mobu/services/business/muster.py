"""Run checks of ingresses and authentication against the Muster server."""

from typing import override

from httpx import AsyncClient, HTTPError, Response
from rubin.repertoire import DiscoveryClient
from safir.sentry import duration
from structlog.stdlib import BoundLogger

from ...events import Events, MusterExecution
from ...exceptions import MusterError, MusterWebError
from ...models.business.muster import MusterOptions
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

__all__ = ["MusterRunner"]


class _NotNone:
    """A helper object that compares equal to everything except None."""

    __hash__ = object.__hash__

    @override
    def __eq__(self, other: object) -> bool:
        return other is not None

    @override
    def __repr__(self) -> str:
        return "<NOT NONE>"


NOT_NONE = _NotNone()
"""An object to indicate that a value can be anything except None."""


class MusterRunner(Business):
    """Check ingresses and authentication against the Muster server.

    The Muster server is a small FastAPI service deployed as a separate
    Phalanx application. It accepts requests behind a variety of different
    authentication rules: unauthenticated, authenticated, with delegated
    tokens, with different Gafaelfawr options, and so forth. It then does some
    server-side checks and returns output that can be checked against mobu's
    expectations.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    discovery_client
        Service discovery client.
    events
        Event publishers.
    logger
        Logger to use to report the results of business.
    flock
        Flock that is running this business, if it is running in a flock.
    """

    def __init__(
        self,
        *,
        options: MusterOptions,
        user: AuthenticatedUser,
        discovery_client: DiscoveryClient,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            discovery_client=discovery_client,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._client: AsyncClient
        self._url: str

    @override
    async def startup(self) -> None:
        headers = {"Authorization": f"Bearer {self.user.token}"}
        self._client = AsyncClient(headers=headers)
        url = await self.discovery.url_for_internal("muster")
        if not url:
            raise MusterError("Service muster not found in service discovery")
        self._url = url
        self.logger.info("Starting Muster runner")

    @override
    async def execute(self) -> None:
        with start_transaction(
            name=f"{self.name} - execute", op="mobu.muster"
        ):
            with capturing_start_span(op="mobu.muster") as span:
                success = False
                try:
                    await self._check_anonymous()
                    await self._check_auth()
                    await self._check_quota()
                    await self._check_delegated()
                    success = True
                finally:
                    event = MusterExecution(
                        success=success,
                        duration=duration(span),
                        **self.common_event_attrs(),
                    )
                    await self.events.muster.publish(event)
                elapsed = duration(span).total_seconds()
            self.logger.info(f"Muster finished after {elapsed} seconds")

    async def _check_anonymous(self) -> None:
        """Check anonymous queries to Muster.

        Most of the check is done on the Muster server side, which verifies
        that Gafaelfawr has stripped out any ``Authorization`` header
        containing a Gafaelfawr token and any cookie named ``gafaelfawr``.
        Mobu currently doesn't have a good way of testing the cookie handling,
        but can test the ``Authorization`` handling by sending a normal
        authenticated request.
        """
        self.logger.info("Checking anonymous access")
        try:
            r = await self._client.get(self._url + "/anonymous")
            r.raise_for_status()
        except HTTPError as e:
            raise MusterWebError.from_exception(e, self.user.username) from e
        if r.json() != {"ok": True}:
            msg = f"Anonymous ingress returned failure: {r.json()!s}"
            raise MusterError(msg)

    async def _check_auth(self) -> None:
        """Check authenticated queries to Muster.

        Muster provides two endpoints, one that will redirect to the login
        server if not authenticated and one that will return a 401 error. Make
        requests to both without an ``Authorization`` header to check that
        behavior, send a request with a bogus ``Authorization`` header to
        check error handling, and then send valid authenticated requests to
        both to check those requests succeed.
        """
        try:
            self.logger.info("Checking redirect for authentication")

            # Redirect with no token.
            request = self._client.build_request(
                "GET", self._url + "/auth/redirect"
            )
            del request.headers["Authorization"]
            r = await self._client.send(request)
            if r.status_code != 302:
                msg = f"Auth redirect returned wrong status: {r.status_code}"
                raise MusterError(msg)

            # 401 challenge with no token.
            self.logger.info("Checking 401 challenge")
            request = self._client.build_request(
                "GET", self._url + "/auth/fail"
            )
            del request.headers["Authorization"]
            r = await self._client.send(request)
            if r.status_code != 401:
                msg = f"Auth failure returned wrong status: {r.status_code}"
                raise MusterError(msg)
            if "WWW-Authenticate" not in r.headers:
                msg = "Auth failure has no WWW-Authenticate header"
                raise MusterError(msg)
            if not r.headers["WWW-Authenticate"].startswith('Bearer realm="'):
                header = r.headers["WWW-Authenticate"]
                msg = f"Auth failure has bad WWW-Authenticate header: {header}"
                raise MusterError(msg)

            # 400 error with bad Authorization header.
            self.logger.info("Checking 400 challenge")
            r = await self._client.get(
                self._url + "/auth/fail",
                headers={"Authorization": "Token bogus"},
            )
            if r.status_code != 400:
                msg = f"Malformed auth returned wrong status: {r.status_code}"
                raise MusterError(msg)

            # Try the endpoints again with a token and they should succeed.
            self.logger.info("Checking successful authentication")
            r = await self._client.get(self._url + "/auth/redirect")
            r.raise_for_status()
            result = r.json()
            r = await self._client.get(self._url + "/auth/fail")
            r.raise_for_status()
        except HTTPError as e:
            raise MusterWebError.from_exception(e, self.user.username) from e

        # Check the results of the two successes with valid auth.
        if result != {"username": self.user.username}:
            msg = f"Bad response from authenticated request: {result!s}"
            raise MusterError(msg)
        if r.json() != result:
            msg = f"Bad response from authenticated request: {result!s}"
            raise MusterError(msg)

    async def _check_quota(self) -> None:
        """Check quota management in Muster."""
        self.logger.info("Checking quota handling")
        expected = {
            "x-ratelimit-limit": "1",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-resource": "muster-quota",
            "x-ratelimit-used": "1",
            "x-ratelimit-reset": NOT_NONE,
        }

        # First run should succeed and return rate limit headers.
        try:
            r = await self._client.get(self._url + "/auth/quota")
            r.raise_for_status()
            headers = self._get_ratelimit_headers(r)
            if headers != expected:
                msg = f"Bad headers from quota request: {headers!s}"
                raise MusterError(msg)

            # Second run should fail with the same headers plus Retry-After.
            r = await self._client.get(self._url + "/auth/quota")
        except HTTPError as e:
            raise MusterWebError.from_exception(e, self.user.username) from e

        # Check that the failure has the right headers and status code.
        if r.status_code != 429:
            msg = f"Bad response from quota rejection: {r.status_code}"
            raise MusterError(msg)
        headers = self._get_ratelimit_headers(r)
        expected["retry-after"] = NOT_NONE
        if headers != expected:
            msg = f"Bad headers from quota rejection: {headers!s}"
            raise MusterError(msg)

    async def _check_delegated(self) -> None:
        """Check token delegation to Muster.

        The Muster server provides two routes, ``/delegated/header`` and
        ``/delegated/authorization``. These are identical from the client
        perspective; the only difference is in the Gafaelfawr configuration
        and thus visible on the server. One of them will add an
        ``Authorization`` header with the delegated token, and the other will
        not.

        This check therefore makes requests to both endpoints and expects them
        both to return the same results.
        """
        self.logger.info("Checking token delegation")
        expected = {
            "username": self.user.username,
            "name": self.user.name,
            "uid": self.user.uidnumber,
            "gid": self.user.gidnumber,
            "groups": [{"name": g.name, "id": g.id} for g in self.user.groups],
        }
        try:
            r = await self._client.get(self._url + "/delegated/header")
            r.raise_for_status()
            result = r.json()
            r = await self._client.get(self._url + "/delegated/authorization")
            r.raise_for_status()
        except HTTPError as e:
            raise MusterWebError.from_exception(e, self.user.username) from e
        if result != expected:
            msg = f"Bad response from delegation: {result!s} != {expected!s}"
            raise MusterError(msg)
        if r.json() != expected:
            msg = (
                f"Bad response from delegation (Authorization): {r.json()!s}"
                f" != {expected!s}"
            )
            raise MusterError(msg)

    def _get_ratelimit_headers(self, response: Response) -> dict[str, str]:
        """Get the rate limit headers from an HTTPX response."""
        return {
            k: v
            for k, v in response.headers.items()
            if k.startswith("x-ratelimit") or k == "retry-after"
        }
