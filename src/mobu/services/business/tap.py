"""Base class for executing TAP queries."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, TypeVar

import pyvo
import requests
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...config import config
from ...exceptions import CodeExecutionError, TAPClientError
from ...models.business.tap import TAPBusinessData, TAPBusinessOptions
from ...models.user import AuthenticatedUser
from .base import Business

T = TypeVar("T", bound="TAPBusinessOptions")

__all__ = ["TAPBusiness"]


class TAPBusiness(Business, Generic[T], metaclass=ABCMeta):
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
    http_client
        Shared HTTP client for general web access.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: T,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._running_query: str | None = None
        self._client: pyvo.dal.TAPService | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)

    async def startup(self) -> None:
        with self.timings.start("make_client"):
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
        query = self.get_next_query()
        with self.timings.start("execute_query", {"query": query}) as sw:
            self._running_query = query

            try:
                if self.options.sync:
                    await self.run_sync_query(query)
                else:
                    await self.run_async_query(query)
            except Exception as e:
                raise CodeExecutionError(
                    user=self.user.username,
                    code=query,
                    code_type="TAP query",
                    error=f"{type(e).__name__}: {e!s}",
                ) from e

            self._running_query = None
            elapsed = sw.elapsed.total_seconds()

        self.logger.info(f"Query finished after {elapsed} seconds")

    async def run_async_query(self, query: str) -> None:
        """Run the query asynchronously.

        Parameters
        ----------
        query
            Query string to execute.
        """
        if not self._client:
            raise RuntimeError("TAPBusiness startup never ran")
        self.logger.info(f"Running (async): {query}")
        job = self._client.submit_job(query)
        try:
            job.run()
            while job.phase not in ("COMPLETED", "ERROR"):
                await asyncio.sleep(30)
        finally:
            job.delete()

    async def run_sync_query(self, query: str) -> None:
        """Run the query synchronously.

        Parameters
        ----------
        query
            Query string to execute.
        """
        if not self._client:
            raise RuntimeError("TAPBusiness startup never ran")
        self.logger.info(f"Running (sync): {query}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._pool, self._client.search, query)

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
        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        tap_url = str(config.environment_url).rstrip("/") + "/api/tap"
        try:
            s = requests.Session()
            s.headers["Authorization"] = "Bearer " + token
            auth = pyvo.auth.AuthSession()
            auth.credentials.set("lsst-token", s)
            auth.add_security_method_for_url(tap_url, "lsst-token")
            auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
            auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
            auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")
            return pyvo.dal.TAPService(tap_url, auth)
        except Exception as e:
            raise TAPClientError(e, user=self.user.username) from e
