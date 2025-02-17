"""Base class for executing TAP queries."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import pyvo
import requests
from safir.sentry import duration
from sentry_sdk import set_context
from structlog.stdlib import BoundLogger

from ...dependencies.config import config_dependency
from ...events import Events, TapQuery
from ...exceptions import TAPClientError
from ...models.business.tap import TAPBusinessData, TAPBusinessOptions
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

__all__ = ["TAPBusiness"]


class TAPBusiness[T: TAPBusinessOptions](Business[T], metaclass=ABCMeta):
    """Base class for business that executes TAP query.

    This class modifies the core `~mobu.business.base.Business` loop by
    providing `startup`, `execute`, and `shutdown` methods that know how to
    execute TAP queries. Subclasses must override `get_next_query` to return
    the next query they want to execute.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    events
        Event publishers.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        *,
        options: T,
        user: AuthenticatedUser,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._running_query: str | None = None
        self._client: pyvo.dal.TAPService | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)

    async def startup(self) -> None:
        self._client = self._make_client(self.user.token)

    @abstractmethod
    def get_next_query(self) -> str:
        """Get the next TAP query to run.

        Returns
        -------
        str
            TAP query as a string.
        """

    async def execute(self) -> None:
        with start_transaction(
            name=f"{self.name} - execute",
            op="mobu.tap.execute",
        ):
            query = self.get_next_query()
            with capturing_start_span(op="mobu.tap.execute_query") as span:
                set_context(
                    "query_info",
                    {"query": query, "started_at": span.start_timestamp},
                )
                self._running_query = query

                success = False
                try:
                    await self.run_query(query)
                    success = True
                finally:
                    await self.events.tap_query.publish(
                        payload=TapQuery(
                            success=success,
                            duration=duration(span),
                            sync=self.options.sync,
                            **self.common_event_attrs(),
                        )
                    )

                self._running_query = None
                elapsed = duration(span).total_seconds()

            self.logger.info(f"Query finished after {elapsed} seconds")

    async def run_query(self, query: str) -> None:
        """Run a TAP query either synchronously or asynchronously.

        Parameters
        ----------
        query
            Query string to execute.
        """
        if not self._client:
            raise RuntimeError("TAPBusiness startup never ran")

        if self.options.sync:
            mode = "(sync)"
            method = self._client.search
        else:
            mode = "(async)"
            method = self._client.run_async

        self.logger.info(f"Running {mode}: {query}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._pool, method, query)

    def dump(self) -> TAPBusinessData:
        return TAPBusinessData(
            running_query=self._running_query, **super().dump().model_dump()
        )

    def _make_client(self, token: str) -> pyvo.dal.TAPService:
        """Create a TAP client.

        Parameters
        ----------
        token
            User authentication token.

        Returns
        -------
        pyvo.dal.TAPService
            TAP client object.
        """
        with capturing_start_span(op="make_client"):
            config = config_dependency.config
            if not config.environment_url:
                raise RuntimeError("environment_url not set")
            tap_url = str(config.environment_url).rstrip("/") + "/api/tap"
            try:
                s = requests.Session()
                s.headers["Authorization"] = "Bearer " + token
                auth = pyvo.auth.AuthSession()
                auth.credentials.set("lsst-token", s)
                auth.add_security_method_for_url(tap_url, "lsst-token")
                auth.add_security_method_for_url(
                    tap_url + "/sync", "lsst-token"
                )
                auth.add_security_method_for_url(
                    tap_url + "/async", "lsst-token"
                )
                auth.add_security_method_for_url(
                    tap_url + "/tables", "lsst-token"
                )
                return pyvo.dal.TAPService(tap_url, auth)
            except Exception as e:
                raise TAPClientError(e) from e
