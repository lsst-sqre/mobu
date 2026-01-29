"""Mock that simulates the Muster service."""

from datetime import datetime, timedelta
from email.utils import format_datetime
from urllib.parse import urljoin

import respx
from httpx import Request, Response
from rubin.gafaelfawr import GafaelfawrClient, GafaelfawrError
from rubin.repertoire import DiscoveryClient
from safir.datetime import current_datetime

__all__ = ["MockMuster", "register_mock_muster"]


class MockMuster:
    """Mock for the Muster API."""

    def __init__(self) -> None:
        self._gafaelfawr = GafaelfawrClient()
        self._rate_limit_count = 0
        self._rate_limit_time: datetime | None = None

    async def aclose(self) -> None:
        """Free any resources allocated by the mock."""
        await self._gafaelfawr.aclose()

    def install_routes(self, respx_mock: respx.Router, base_url: str) -> None:
        """Install the mock routes for the Muster API.

        Parameters
        ----------
        respx_mock
            Mock router to use to install routes.
        base_url
            Base URL for the mock routes.
        """
        prefix = base_url.rstrip("/") + "/"
        handler = self._handle_anonymous
        respx_mock.get(urljoin(prefix, "anonymous")).mock(side_effect=handler)
        handler = self._handle_auth_fail
        respx_mock.get(urljoin(prefix, "auth/fail")).mock(side_effect=handler)
        handler = self._handle_auth_redirect
        route = urljoin(prefix, "auth/redirect")
        respx_mock.get(route).mock(side_effect=handler)
        handler = self._handle_auth_quota
        respx_mock.get(urljoin(prefix, "auth/quota")).mock(side_effect=handler)
        handler = self._handle_delegated
        route = urljoin(prefix, "delegated/header")
        respx_mock.get(route).mock(side_effect=handler)
        route = urljoin(prefix, "delegated/authorization")
        respx_mock.get(route).mock(side_effect=handler)

    async def _handle_anonymous(self, request: Request) -> Response:
        return Response(200, json={"ok": True})

    async def _handle_auth_fail(self, request: Request) -> Response:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(
                401,
                headers={
                    "WWW-Authenticate": 'Bearer realm="data.example.com"'
                },
            )
        method, token = authorization.split(" ")
        if method.lower() != "bearer":
            return Response(400)
        try:
            user_info = await self._gafaelfawr.get_user_info(token)
        except GafaelfawrError:
            return Response(401)
        result = {"username": user_info.username}
        if user_info.email:
            result["email"] = user_info.email
        return Response(200, json=result)

    async def _handle_auth_redirect(self, request: Request) -> Response:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(
                302, headers={"Location": "https://example.com/login"}
            )
        _, token = authorization.split(" ")
        user_info = await self._gafaelfawr.get_user_info(token)
        result = {"username": user_info.username}
        if user_info.email:
            result["email"] = user_info.email
        return Response(200, json=result)

    async def _handle_auth_quota(self, request: Request) -> Response:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(401)
        now = current_datetime()
        if self._rate_limit_time and now > self._rate_limit_time:
            self._rate_limit_count = 0
            self._rate_limit_time = now + timedelta(minutes=1)
        elif not self._rate_limit_time:
            self._rate_limit_time = now + timedelta(minutes=1)
        self._rate_limit_count += 1
        reset = self._rate_limit_time
        headers = {
            "X-RateLimit-Limit": "1",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(reset.timestamp())),
            "X-RateLimit-Resource": "muster-quota",
            "X-RateLimit-Used": "1",
        }
        if self._rate_limit_count >= 2:
            return Response(
                429,
                headers={
                    "Retry-After": format_datetime(reset, usegmt=True),
                    **headers,
                },
            )
        _, token = authorization.split(" ")
        user_info = await self._gafaelfawr.get_user_info(token)
        result = {"username": user_info.username}
        if user_info.email:
            result["email"] = user_info.email
        return Response(200, json=result, headers=headers)

    async def _handle_delegated(self, request: Request) -> Response:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(401)
        _, token = authorization.split(" ")
        user_info = await self._gafaelfawr.get_user_info(token)
        groups = [{"name": g.name, "id": g.id} for g in user_info.groups]
        result = {
            "username": user_info.username,
            "name": user_info.name,
            "uid": user_info.uid,
            "gid": user_info.gid,
            "groups": groups,
        }
        if user_info.email:
            result["email"] = user_info.email
        return Response(200, json=result)


async def register_mock_muster(respx_mock: respx.Router) -> MockMuster:
    """Mock out Muster.

    Parameters
    ----------
    respx_mock
        Mock router.

    Returns
    -------
    MockGafaelfawr
        Mock Gafaelfawr API object.
    """
    discovery_client = DiscoveryClient()
    url = await discovery_client.url_for_internal("muster")
    await discovery_client.aclose()
    assert url, "Service muster not found in Repertoire"
    mock = MockMuster()
    mock.install_routes(respx_mock, url)
    return mock
