import asyncio
import os
import random
import time

import jinja2
import pyvo
import requests
from pyvo.auth import AuthSession

from mobu.business import Business
from mobu.config import Configuration


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
    success_count: int = 0
    failure_count: int = 0

    def _client(self) -> pyvo.dal.TAPService:
        tap_url = Configuration.environment_url + "/api/tap"

        s = requests.Session()
        s.headers["Authorization"] = "Bearer " + self.monkey.user.token
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
            logger = self.monkey.log
            logger.info("Starting up...")

            template_dir = os.path.join(
                os.path.dirname(__file__), "static/querymonkey/"
            )
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                undefined=jinja2.StrictUndefined,
            )
            logger.info(
                "Query templates to choose from: %s", env.list_templates()
            )

            service = self._client()

            while True:
                template_name = random.choice(env.list_templates())
                template = env.get_template(template_name)
                query = template.render(generate_parameters())
                logger.info("Running: %s", query)
                start = time.time()
                await loop.run_in_executor(None, service.search, query)
                end = time.time()
                logger.info("Finished, took: %i seconds", end - start)
                self.success_count += 1
                await asyncio.sleep(60)
        except Exception:
            self.failure_count += 1
            raise

    def dump(self) -> dict:
        return {
            "name": "QueryMonkey",
            "failure_count": self.failure_count,
            "success_count": self.success_count,
        }
