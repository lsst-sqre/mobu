"""Run a set of predefined queries against a SIA service."""

from __future__ import annotations

import importlib.resources
from random import SystemRandom

import jinja2
import yaml
from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.sia import SIA2SearchParameters
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

        # Load templates and parameters. The path has to be specified in two
        # different ways: as a relative path for Jinja's PackageLoader, and as
        # a sequence of joinpath operations for importlib.resources.
        template_path = ("data", "siaquerysetrunner", self.options.query_set)
        self._env = jinja2.Environment(
            loader=jinja2.PackageLoader("mobu", "/".join(template_path)),
            undefined=jinja2.StrictUndefined,
            autoescape=jinja2.select_autoescape(disabled_extensions=["sql"]),
        )
        files = importlib.resources.files("mobu")
        for directory in template_path:
            files = files.joinpath(directory)
        with files.joinpath("params.yaml").open("r") as f:
            self._params = yaml.safe_load(f)

    async def startup(self) -> None:
        await super().startup()
        self.logger.info("Starting SIA Query Set Runner")

    def get_next_query(self) -> SIA2SearchParameters:
        """Generate a random SIAv2 Query using the stored param ranges.

        Returns
        -------
        SIA2SearchParameters
            Next SIA query to run.
        """
        return self._generate_siav2_params()

    def _generate_siav2_params(
        self,
    ) -> SIA2SearchParameters:
        """Generate a random SIAv2 query."""
        min_ra = self._params.get("min_ra", 55.0)
        max_ra = self._params.get("max_ra", 70.0)
        min_dec = self._params.get("min_dec", -42.0)
        max_dec = self._params.get("max_dec", -30.0)
        min_radius = self._params.get("min_radius", 0.01)
        radius_range = self._params.get("radius_range", 0.04)
        start_time = self._params.get("start_time", 60550.31803461111)
        end_time = self._params.get("end_time", 60550.31838182871)

        ra = min_ra + self._random.random() * (max_ra - min_ra)
        dec = min_dec + self._random.random() * (max_dec - min_dec)
        radius = min_radius + self._random.random() * radius_range

        return SIA2SearchParameters(
            ra=ra,
            dec=dec,
            radius=radius,
            time=[start_time, end_time],
        )
