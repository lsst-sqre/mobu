"""Run a set of predefined queries against a SIA service."""

from __future__ import annotations

import asyncio
import importlib.resources
from concurrent.futures import ThreadPoolExecutor
from random import SystemRandom
from typing import override

import pyvo
import requests
import yaml
from rubin.repertoire import DiscoveryClient
from safir.sentry import duration
from sentry_sdk import set_context
from structlog.stdlib import BoundLogger

from ...events import Events
from ...events import SIAQuery as SIAQueryEvent
from ...exceptions import ServiceDiscoveryError, SIAClientError
from ...models.business.siaquerysetrunner import (
    SIABusinessData,
    SIAQuery,
    SIAQuerySetRunnerOptions,
)
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

__all__ = ["SIAQuerySetRunner"]


class SIAQuerySetRunner(Business):
    """Run queries from a predefined set against SIA with random parameters.

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
        options: SIAQuerySetRunnerOptions,
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
        self._running_query: SIAQuery | None = None
        self._client: pyvo.dal.SIA2Service | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._random = SystemRandom()
        self.query_set: str = self.options.query_set

        # Load parameters. We don't need jinja here since we're not
        # generating queries, just parameters from the ranges.
        params_path = importlib.resources.files("mobu").joinpath(
            "data", "siaquerysetrunner", self.options.query_set, "params.yaml"
        )
        with params_path.open("r") as f:
            self._params = yaml.safe_load(f)

    @override
    async def startup(self) -> None:
        self._client = await self._make_client(self.user.token)
        self.logger.info("Starting SIA Query Set Runner")

    def get_next_query(self) -> SIAQuery:
        """Get the next SIA query to run.

        Returns
        -------
        mobu.models.business.siaquerysetrunner.SIAQuery
            SIA query as an SIAQuery object.
        """
        return self._generate_sia_params()

    @override
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
                    client = self._client
                    if not client:
                        raise RuntimeError(
                            "SIAQuerySetRunner startup never ran"
                        )
                    self.logger.info(f"Running SIA query: {query}")
                    loop = asyncio.get_event_loop()

                    await loop.run_in_executor(
                        self._pool,
                        lambda: client.search(**query.to_pyvo_sia_params()),
                    )
                    success = True
                finally:
                    await self.events.sia_query.publish(
                        payload=SIAQueryEvent(
                            success=success,
                            duration=duration(span),
                            **self.common_event_attrs(),
                        )
                    )

                self._running_query = None
                elapsed = duration(span).total_seconds()

            self.logger.info(f"Query finished after {elapsed} seconds")

    @override
    def dump(self) -> SIABusinessData:
        return SIABusinessData(
            running_query=self._running_query, **super().dump().model_dump()
        )

    async def _make_client(self, token: str) -> pyvo.dal.SIA2Service:
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
        dataset = self.options.dataset
        with capturing_start_span(op="make_client"):
            url = await self.discovery.url_for_data("sia", dataset)
            if not url:
                msg = f"SIA for {dataset} not found in service discovery"
                raise ServiceDiscoveryError(msg)
            try:
                session = requests.Session()
                session.headers["Authorization"] = "Bearer " + token
                auth = pyvo.auth.AuthSession()
                auth.credentials.set("lsst-token", session)
                auth.add_security_method_for_url(url + "/query", "lsst-token")
                return pyvo.dal.SIA2Service(url, session=auth)
            except Exception as e:
                raise SIAClientError(e) from e

    def _generate_sia_params(
        self,
    ) -> SIAQuery:
        """Generate a random SIA (v2) query."""
        min_ra = self._params.get("min_ra", 55.0)
        max_ra = self._params.get("max_ra", 70.0)
        min_dec = self._params.get("min_dec", -42.0)
        max_dec = self._params.get("max_dec", -30.0)
        min_radius = self._params.get("min_radius", 0.01)
        radius_range = self._params.get("radius_range", 0.04)
        start_time = self._params.get("start_time", 60550.31803461111)
        end_time = self._params.get("end_time", 60550.31838182871)

        ra = min_ra + self._random.uniform(min_ra, max_ra)
        dec = min_dec + self._random.uniform(min_dec, max_dec)
        radius = self._random.uniform(min_radius, min_radius + radius_range)

        return SIAQuery(
            ra=ra,
            dec=dec,
            radius=radius,
            time=[start_time, end_time],
        )
