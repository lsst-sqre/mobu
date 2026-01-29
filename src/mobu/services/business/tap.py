"""Base class for executing TAP queries."""

import asyncio
import contextlib
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import override

import pyvo
import requests
from rubin.repertoire import DiscoveryClient
from safir.sentry import duration
from sentry_sdk import set_context
from structlog.stdlib import BoundLogger

from ...events import Events, TapQuery
from ...exceptions import ServiceDiscoveryError, TAPClientError
from ...models.business.tap import TAPBusinessData, TAPBusinessOptions
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

__all__ = ["TAPBusiness"]


class TAPBusiness[T: TAPBusinessOptions](Business[T], metaclass=ABCMeta):
    """Base class for business that executes TAP query.

    This class modifies the core `~mobu.services.business.base.Business` loop
    by providing `startup`, `execute`, and ``shutdown`` methods that know how
    to execute TAP queries. Subclasses must override `get_next_query` to return
    the next query they want to execute.

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
    """

    def __init__(
        self,
        *,
        options: T,
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
        self._running_query: str | None = None
        self._client: pyvo.dal.TAPService | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)

    @override
    async def startup(self) -> None:
        self._client = await self._make_client(self.user.token)

    @abstractmethod
    def get_next_query(self) -> str:
        """Get the next TAP query to run.

        Returns
        -------
        str
            TAP query as a string.
        """

    @override
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

        loop = asyncio.get_event_loop()

        if self.options.sync:
            self.logger.info(f"Running (sync): {query}")
            await loop.run_in_executor(self._pool, self._client.search, query)
        else:
            self.logger.info(f"Running (async): {query}")
            await loop.run_in_executor(self._pool, self._run_async_job, query)

    def _run_async_job(self, query: str) -> None:
        """Run an async TAP job with optional timeout.

        This method submits a job, waits for completion with an optional
        timeout and then cleans up the job. If a timeout occurs the job is
        aborted and we raise an Exception.

        Parameters
        ----------
        query
            Query string to execute.
        """
        if not self._client:
            raise RuntimeError("TAPBusiness startup never ran")

        job = self._client.submit_job(query)
        try:
            job.run()
            if self.options.query_timeout is not None:
                job.wait(
                    phases=["COMPLETED", "ERROR", "ABORTED"],
                    timeout=self.options.query_timeout,
                )
            else:
                job.wait(phases=["COMPLETED", "ERROR", "ABORTED"])
            job.raise_if_error()
            job.fetch_result()
        except Exception:
            if job.phase in ("QUEUED", "EXECUTING"):
                with contextlib.suppress(Exception):
                    job.abort()
            raise
        finally:
            with contextlib.suppress(Exception):
                job.delete()

    @override
    def dump(self) -> TAPBusinessData:
        return TAPBusinessData(
            running_query=self._running_query, **super().dump().model_dump()
        )

    async def _make_client(self, token: str) -> pyvo.dal.TAPService:
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
        dataset = self.options.dataset
        with capturing_start_span(op="make_client"):
            url = await self.discovery.url_for_data("tap", dataset)
            if not url:
                msg = f"TAP for {dataset} not found in service discovery"
                raise ServiceDiscoveryError(msg)
            try:
                session = requests.Session()
                session.headers["Authorization"] = "Bearer " + token
                auth = pyvo.auth.AuthSession()
                auth.credentials.set("lsst-token", session)
                auth.add_security_method_for_url(url, "lsst-token")
                auth.add_security_method_for_url(url + "/sync", "lsst-token")
                auth.add_security_method_for_url(url + "/async", "lsst-token")
                auth.add_security_method_for_url(url + "/tables", "lsst-token")
                return pyvo.dal.TAPService(url, session=auth)
            except Exception as e:
                raise TAPClientError(e) from e
