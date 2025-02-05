"""Base class for executing SIA queries."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, TypeVar

import pyvo
import requests
from safir.sentry import duration
from sentry_sdk import set_context
from structlog.stdlib import BoundLogger

from ...dependencies.config import config_dependency
from ...events import Events, SIAQuery
from ...exceptions import SIAClientError
from ...models.business.sia import (
    SIA2SearchParameters,
    SIABusinessData,
    SIABusinessOptions,
)
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

T = TypeVar("T", bound="SIABusinessOptions")

__all__ = ["SIABusiness"]


class SIABusiness(Business, Generic[T], metaclass=ABCMeta):
    """Base class for business that executes SIA query.

    This class modifies the core `~mobu.business.base.Business` loop by
    providing `startup`, `execute`, and `shutdown` methods that know how to
    execute SIA queries. Subclasses must override `get_next_query` to return
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
        self._running_query: SIA2SearchParameters | None = None
        self._client: pyvo.dal.SIA2Service | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)
        self.query_set: str = self.options.query_set

    async def startup(self) -> None:
        self._client = self._make_client(self.user.token)

    @abstractmethod
    def get_next_query(self) -> SIA2SearchParameters:
        """Get the next SIA query to run.

        Returns
        -------
        SIA2SearchParameters
            SIA query as an SIA2SearchParameters object.
        """

    async def execute(self) -> None:
        with start_transaction(
            name=f"{self.name} - execute",
            op="mobu.sia.search",
        ):
            query = self.get_next_query()
            with capturing_start_span(op="mobu.sia.search") as span:
                set_context(
                    "query_info",
                    {"query": str(query), "started_at": span.start_timestamp},
                )
                self._running_query = query

                success = False
                try:
                    if not self._client:
                        raise RuntimeError("SIABusiness startup never ran")
                    self.logger.info(f"Running SIA query: {query}")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        self._pool,
                        self._client.search,
                        query.to_pyvo_sia2_params(),
                    )
                    success = True
                finally:
                    await self.events.sia_query.publish(
                        payload=SIAQuery(
                            success=success,
                            duration=duration(span),
                            **self.common_event_attrs(),
                        )
                    )

                self._running_query = None
                elapsed = duration(span).total_seconds()

            self.logger.info(f"Query finished after {elapsed} seconds")

    def dump(self) -> SIABusinessData:
        return SIABusinessData(
            running_query=self._running_query, **super().dump().model_dump()
        )

    def _make_client(self, token: str) -> pyvo.dal.SIA2Service:
        """Create a SIA client.

        Parameters
        ----------
        token
            User authentication token.

        Returns
        -------
        pyvo.dal.SIA2Service
            SIA2Service client object.
        """
        with capturing_start_span(op="make_client"):
            config = config_dependency.config
            if not config.environment_url:
                raise RuntimeError("environment_url not set")
            sia_url = (
                f"{str(config.environment_url).rstrip('/')}/api/sia/"
                f"{self.query_set}"
            )

            try:
                s = requests.Session()
                s.headers["Authorization"] = "Bearer " + token
                auth = pyvo.auth.AuthSession()
                auth.credentials.set("lsst-token", s)
                auth.add_security_method_for_url(
                    sia_url + "/query", "lsst-token"
                )
                return pyvo.dal.SIA2Service(sia_url, auth)
            except Exception as e:
                raise SIAClientError(e) from e
