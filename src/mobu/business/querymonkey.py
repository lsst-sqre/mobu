from __future__ import annotations

import asyncio
import os
import random
from typing import TYPE_CHECKING

import jinja2
import pyvo
import requests
from pyvo.auth import AuthSession

from mobu.business.base import Business
from mobu.config import Configuration

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

    @staticmethod
    def _make_client(token: str) -> pyvo.dal.TAPService:
        tap_url = Configuration.environment_url + "/api/tap"

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
        try:
            loop = asyncio.get_event_loop()
            self.logger.info("Starting up...")

            template_dir = os.path.join(
                os.path.dirname(__file__), "static/querymonkey/"
            )
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                undefined=jinja2.StrictUndefined,
            )
            self.logger.info(
                "Query templates to choose from: %s", env.list_templates()
            )

            while True:
                template_name = random.choice(env.list_templates())
                template = env.get_template(template_name)
                query = template.render(generate_parameters())
                self.logger.info("Running: %s", query)
                self.start_event("execute_query")
                await loop.run_in_executor(None, self._client.search, query)
                sw = self.get_current_event()
                elapsed = "???"
                if sw is not None:
                    sw.annotation = {"query": query}
                    elapsed = str(sw.elapsed)
                self.stop_current_event()
                self.logger.info(f"Query finished after {elapsed} seconds")
                self.success_count += 1
                await asyncio.sleep(60)
        except Exception:
            self.failure_count += 1
            raise

    async def stop(self) -> None:
        loop = asyncio.get_event_loop()
        self.start_event("delete_tap_client_on_stop")
        await loop.run_in_executor(None, self._client.abort)
        await loop.run_in_executor(None, self._client.delete)
        self.stop_current_event()
