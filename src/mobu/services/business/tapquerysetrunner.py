"""Run a set of predefined queries against a TAP service."""

from __future__ import annotations

import importlib.resources
import math
from random import SystemRandom

import jinja2
import shortuuid
import yaml
from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.tapquerysetrunner import TAPQuerySetRunnerOptions
from ...models.user import AuthenticatedUser
from .tap import TAPBusiness

__all__ = ["TAPQuerySetRunner"]


class TAPQuerySetRunner(TAPBusiness):
    """Run queries from a predefined set against TAP with random parameters.

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
        options: TAPQuerySetRunnerOptions,
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
        template_path = ("data", "tapquerysetrunner", self.options.query_set)
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
        templates = self._env.list_templates(["sql"])
        self.logger.info("Query templates to choose from: %s", templates)

    def get_next_query(self) -> str:
        """Choose a random query from the query set.

        Returns
        -------
        str
            Next TAP query to run.
        """
        template_name = self._random.choice(self._env.list_templates(["sql"]))
        template = self._env.get_template(template_name)
        return template.render(self._generate_parameters())

    def _generate_random_polygon(
        self,
        *,
        min_ra: float,
        max_ra: float,
        min_dec: float,
        max_dec: float,
        min_radius: float,
        radius_range: float,
    ) -> str:
        """Generate a random polygon as comma-separated ra/dec values."""
        ra = min_ra + self._random.random() * (max_ra - min_ra)
        dec = min_dec + self._random.random() * (max_dec - min_dec)
        r = min_radius + self._random.random() * radius_range
        n = self._random.randrange(3, 8)
        phi = self._random.random() * 2 * math.pi
        poly = []
        for theta in [phi + i * 2 * math.pi / n for i in range(n)]:
            poly.append(ra + r * math.sin(theta))
            poly.append(dec + r * math.cos(theta))
        return ", ".join([str(x) for x in poly])

    def _generate_parameters(self) -> dict[str, int | float | str]:
        """Generate some random parameters for the query."""
        min_ra = self._params.get("min_ra", 55.0)
        max_ra = self._params.get("max_ra", 70.0)
        min_dec = self._params.get("min_dec", -42.0)
        max_dec = self._params.get("max_dec", -30.0)
        min_radius = self._params.get("min_radius", 0.01)
        radius_range = self._params.get("radius_range", 0.04)
        radius_near_range = self._params.get("radius_near_range", 0.09)
        min_flux = 0.0 + self._random.random() * 0.00100
        min_mag = 15.0 + self._random.random() * 15.0
        result = {
            "ra": min_ra + self._random.random() * (max_ra - min_ra),
            "dec": min_dec + self._random.random() * (max_dec - min_dec),
            "min_flux": min_flux,
            "max_flux": min_flux + 0.00001,
            "min_mag": min_mag,
            "max_mag": min_mag + 0.1,
            "polygon": self._generate_random_polygon(
                min_ra=min_ra,
                max_ra=max_ra,
                min_dec=min_dec,
                max_dec=max_dec,
                min_radius=min_radius,
                radius_range=radius_range,
            ),
            "radius": min_radius + self._random.random() * radius_range,
            "radius_near": (
                min_radius + self._random.random() * radius_near_range
            ),
            "username": self.user.username,
            "query_id": "mobu-" + shortuuid.uuid(),
        }
        object_ids = self._params.get("object_ids")
        if object_ids:
            result["object"] = str(self._random.choice(object_ids))
            result["objects"] = ", ".join(
                str(o) for o in self._random.choices(object_ids, k=12)
            )
        return result
