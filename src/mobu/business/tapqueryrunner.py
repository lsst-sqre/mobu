"""Run queries against a TAP service."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import pyvo
import requests

from ..config import config
from ..exceptions import CodeExecutionError
from .base import Business

if TYPE_CHECKING:
    from typing import Any, Dict, Optional

    from structlog import BoundLogger

    from ..models.business import BusinessConfig, BusinessData
    from ..models.user import AuthenticatedUser


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

        template_path = (
            Path(__file__).parent.parent / "templates" / "tapqueryrunner"
        )
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path)),
            undefined=jinja2.StrictUndefined,
        )

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
    def _generate_parameters() -> Dict[str, Any]:
        """Generate some random parameters for the query."""
        return {
            "limit_dec": lambda x: max(min(x, 90), -90),
            "ra": random.uniform(0, 360),
            "dec": random.uniform(-90, 90),
            "r1": random.uniform(0, 1),
            "r2": random.uniform(0, 1),
            "r3": random.uniform(0, 1),
            "r4": random.uniform(0, 1),
            "rsmall": random.uniform(0, 0.25),
        }

    async def startup(self) -> None:
        templates = self._env.list_templates()
        self.logger.info("Query templates to choose from: %s", templates)

    async def execute(self) -> None:
        template_name = random.choice(self._env.list_templates())
        template = self._env.get_template(template_name)
        query = template.render(self._generate_parameters())
        await self.run_query(query)

    async def run_query(self, query: str) -> None:
        self.logger.info("Running: %s", query)
        loop = asyncio.get_event_loop()
        with self.timings.start("execute_query", {"query": query}) as sw:
            self.running_query = query
            try:
                await loop.run_in_executor(None, self._client.search, query)
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
