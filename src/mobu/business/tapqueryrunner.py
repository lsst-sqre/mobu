"""Run queries against a TAP service."""

from __future__ import annotations

import asyncio
import math
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional, Union

import jinja2
import pyvo
import requests
import yaml
from structlog import BoundLogger

from ..config import config
from ..exceptions import CodeExecutionError
from ..models.business import BusinessConfig, BusinessData
from ..models.user import AuthenticatedUser
from .base import Business


class TAPQueryRunner(Business):
    """Run queries against TAP."""

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        self.running_query: Optional[str] = None
        self._client = self._make_client(user.token)
        self._pool = ThreadPoolExecutor(max_workers=1)

        template_path = (
            Path(__file__).parent.parent / "templates" / "tapqueryrunner"
        )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path)),
            undefined=jinja2.StrictUndefined,
        )
        with (template_path / "objects.yaml").open("r") as f:
            self._objects = yaml.safe_load(f)

    @staticmethod
    def _make_client(token: str) -> pyvo.dal.TAPService:
        tap_url = config.environment_url + "/api/tap"

        s = requests.Session()
        s.headers["Authorization"] = "Bearer " + token
        auth = pyvo.auth.AuthSession()
        auth.credentials.set("lsst-token", s)
        auth.add_security_method_for_url(tap_url, "lsst-token")
        auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
        auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
        auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")

        return pyvo.dal.TAPService(tap_url, auth)

    @staticmethod
    def _generate_random_polygon() -> str:
        """Generate a random polygon as comma-separated ra/dec values."""
        ra = 55.0 + random.random() * 15.0
        dec = -42.0 + random.random() * 12.0
        r = 0.01 + random.random() * 0.04
        n = random.randrange(3, 8)
        phi = random.random() * 2 * math.pi
        poly = []
        for theta in [phi + i * 2 * math.pi / n for i in range(n)]:
            poly.append(ra + r * math.sin(theta))
            poly.append(dec + r * math.cos(theta))
        return ", ".join([str(x) for x in poly])

    def _generate_parameters(self) -> Dict[str, Union[int, float, str]]:
        """Generate some random parameters for the query."""
        min_flux = 0.0 + random.random() * 0.00100
        min_mag = 15.0 + random.random() * 15.0
        return {
            "ra": 55.0 + random.random() * 15.0,
            "dec": -42.0 + random.random() * 12.0,
            "min_flux": min_flux,
            "max_flux": min_flux + 0.00001,
            "min_mag": min_mag,
            "max_mag": min_mag + 0.1,
            "object": str(random.choice(self._objects)),
            "objects": ", ".join(
                str(o) for o in random.choices(self._objects, k=12)
            ),
            "polygon": self._generate_random_polygon(),
            "radius": 0.01 + random.random() * 0.04,
            "radius_near": 0.01 + random.random() * 0.09,
        }

    async def startup(self) -> None:
        templates = self._env.list_templates(["sql"])
        self.logger.info("Query templates to choose from: %s", templates)

    async def execute(self) -> None:
        template_name = random.choice(self._env.list_templates(["sql"]))
        template = self._env.get_template(template_name)
        query = template.render(self._generate_parameters())
        await self.run_query(query)

    async def run_query(self, query: str) -> None:
        self.logger.info("Running: %s", query)
        loop = asyncio.get_event_loop()
        with self.timings.start("execute_query", {"query": query}) as sw:
            self.running_query = query
            try:
                await loop.run_in_executor(
                    self._pool, self._client.search, query
                )
            except Exception as e:
                user = self.user.username
                error = f"{type(e).__name__}: {str(e)}"
                raise CodeExecutionError(
                    user, query, code_type="TAP query", error=error
                ) from e
            self.running_query = None
            elapsed = sw.elapsed.total_seconds()
        self.logger.info(f"Query finished after {elapsed} seconds")

    def dump(self) -> BusinessData:
        data = super().dump()
        data.running_code = self.running_query
        return data
