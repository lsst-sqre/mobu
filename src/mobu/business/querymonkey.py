from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import pyvo
import requests
from pyvo.auth import AuthSession

from ..config import config
from .base import Business

if TYPE_CHECKING:
    from typing import Any, Dict

    from structlog import BoundLogger

    from ..user import User


def limit_dec(x: int) -> int:
    return max(min(x, 90), -90)


def generate_parameters() -> dict:
    return {
        "limit_dec": limit_dec,
        "ra": random.uniform(0, 360),
        "dec": random.uniform(-90, 90),
        "r1": random.uniform(0, 1),
        "r2": random.uniform(0, 1),
        "r3": random.uniform(0, 1),
        "r4": random.uniform(0, 1),
        "rsmall": random.uniform(0, 0.25),
    }


class QueryMonkey(Business):
    """Run queries against TAP."""

    def __init__(
        self, logger: BoundLogger, options: Dict[str, Any], user: User
    ) -> None:
        super().__init__(logger, options, user)
        self._client = self._make_client(user.token)
        template_path = Path(__file__).parent.parent / "static" / "querymonkey"
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path)),
            undefined=jinja2.StrictUndefined,
        )

    @staticmethod
    def _make_client(token: str) -> pyvo.dal.TAPService:
        tap_url = config.environment_url + "/api/tap"

        s = requests.Session()
        s.headers["Authorization"] = "Bearer " + token
        auth = AuthSession()
        auth.credentials.set("lsst-token", s)
        auth.add_security_method_for_url(tap_url, "lsst-token")
        auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
        auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
        auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")

        return pyvo.dal.TAPService(tap_url, auth)

    async def run(self) -> None:
        self.logger.info("Starting up...")
        templates = self._env.list_templates()
        self.logger.info("Query templates to choose from: %s", templates)

        while True:
            template_name = random.choice(self._env.list_templates())
            template = self._env.get_template(template_name)
            query = template.render(generate_parameters())
            try:
                await self.run_query(query)
                self.success_count += 1
            except Exception:
                self.failure_count += 1
                raise
            await asyncio.sleep(60)

    async def run_query(self, query: str) -> None:
        self.logger.info("Running: %s", query)
        loop = asyncio.get_event_loop()
        with self.timings.start("execute_query", {"query": query}) as sw:
            await loop.run_in_executor(None, self._client.search, query)
            elapsed = sw.elapsed.total_seconds()
        self.logger.info(f"Query finished after {elapsed} seconds")

    async def stop(self) -> None:
        loop = asyncio.get_event_loop()
        with self.timings.start("delete_tap_client_on_stop"):
            await loop.run_in_executor(None, self._client.abort)
            await loop.run_in_executor(None, self._client.delete)
