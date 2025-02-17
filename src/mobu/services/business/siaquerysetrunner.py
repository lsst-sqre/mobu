"""Run a set of predefined queries against a SIA service."""

from __future__ import annotations

import importlib.resources
from random import SystemRandom

import yaml
from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.sia import SIA2Query
from ...models.business.siaquerysetrunner import SIAQuerySetRunnerOptions
from ...models.user import AuthenticatedUser
from .sia import SIABusiness

__all__ = ["SIAQuerySetRunner"]


class SIAQuerySetRunner(SIABusiness):
    """Run queries from a predefined set against SIA with random parameters.

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
    flock
        Flock that is running this business, if it is running in a flock.
    """

    def __init__(
        self,
        *,
        options: SIAQuerySetRunnerOptions,
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
        self._random = SystemRandom()

        # Load parameters. We don't need jinja here since we're not
        # generating queries, just parameters from the ranges.
        params_path = importlib.resources.files("mobu").joinpath(
            "data", "siaquerysetrunner", self.options.query_set, "params.yaml"
        )
        with params_path.open("r") as f:
            self._params = yaml.safe_load(f)

    async def startup(self) -> None:
        await super().startup()
        self.logger.info("Starting SIA Query Set Runner")

    def get_next_query(self) -> SIA2Query:
        """Generate a random SIAv2 Query using the stored param ranges.

        Returns
        -------
        SIA2Query
            Next SIA query to run.
        """
        return self._generate_siav2_params()

    def _generate_siav2_params(
        self,
    ) -> SIA2Query:
        """Generate a random SIAv2 query."""
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

        return SIA2Query(
            ra=ra,
            dec=dec,
            radius=radius,
            time=[start_time, end_time],
        )
