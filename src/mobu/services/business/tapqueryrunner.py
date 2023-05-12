"""Run queries against a TAP service."""

from __future__ import annotations

import asyncio
import importlib.resources
import math
from concurrent.futures import ThreadPoolExecutor
from random import SystemRandom

import jinja2
import pyvo
import requests
import shortuuid
import yaml
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...config import config
from ...exceptions import CodeExecutionError, TAPClientError
from ...models.business.tapqueryrunner import (
    TAPQueryRunnerData,
    TAPQueryRunnerOptions,
)
from ...models.user import AuthenticatedUser
from .base import Business


class TAPQueryRunner(Business):
    """Run queries against TAP.

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
        options: TAPQueryRunnerOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._running_query: str | None = None
        self._client: pyvo.dal.TAPService | None = None
        self._random = SystemRandom()
        self._pool = ThreadPoolExecutor(max_workers=1)

        # Load templates and parameters. The path has to be specified in two
        # different ways: as a relative path for Jinja's PackageLoader, and as
        # a sequence of joinpath operations for importlib.resources.
        template_path = ("data", "tapqueryrunner", options.query_set)
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
        templates = self._env.list_templates(["sql"])
        self.logger.info("Query templates to choose from: %s", templates)
        with self.timings.start("make_client"):
            self._client = self._make_client(self.user.token)

    async def execute(self) -> None:
        template_name = self._random.choice(self._env.list_templates(["sql"]))
        template = self._env.get_template(template_name)
        query = template.render(self._generate_parameters())

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
                    error=f"{type(e).__name__}: {str(e)}",
                ) from e

            self._running_query = None
            elapsed = sw.elapsed.total_seconds()

        self.logger.info(f"Query finished after {elapsed} seconds")

    async def run_async_query(self, query: str) -> None:
        if not self._client:
            raise RuntimeError("TAPQueryRunner startup never ran")
        self.logger.info("Running (async): %s", query)
        job = self._client.submit_job(query)
        try:
            job.run()
            while job.phase not in ("COMPLETED", "ERROR"):
                await asyncio.sleep(30)
        finally:
            job.delete()

    async def run_sync_query(self, query: str) -> None:
        if not self._client:
            raise RuntimeError("TAPQueryRunner startup never ran")
        self.logger.info("Running (sync): %s", query)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._pool, self._client.search, query)

    def dump(self) -> TAPQueryRunnerData:
        return TAPQueryRunnerData(
            running_query=self._running_query, **super().dump().dict()
        )

    def _make_client(self, token: str) -> pyvo.dal.TAPService:
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
