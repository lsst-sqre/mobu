import asyncio
import os
import random
import time
from dataclasses import field

import jinja2
import pyvo
import requests
from pyvo.auth import AuthSession

from mobu.businesstime import BusinessTime
from mobu.config import Configuration
from mobu.timing import QueryTimingData, TAPQueryTimingData, TimeInfo


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


class QueryMonkey(BusinessTime):
    success_count: int = 0
    failure_count: int = 0
    _client: pyvo.dal.TAPService = field(init=False)

    def _make_client(self) -> pyvo.dal.TAPService:
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

            self._client = self._make_client()
            stamp = TAPQueryTimingData(start=TimeInfo.stamp())
            while True:
                template_name = random.choice(env.list_templates())
                template = env.get_template(template_name)
                query = template.render(generate_parameters())
                logger.info("Running: %s", query)
                start = time.time()
                qt = QueryTimingData(start=TimeInfo.stamp(), query=query)
                stamp.query.append(qt)
                await loop.run_in_executor(None, self._client.search, query)
                qt.stop = TimeInfo.stamp(previous=qt.start)
                end = time.time()
                logger.info("Finished, took: %i seconds", end - start)
                self.success_count += 1
                await asyncio.sleep(60)
        except Exception:
            self.failure_count += 1
            raise

    async def stop(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._client.abort)
        await loop.run_in_executor(None, self._client.delete)

    def dump(self) -> dict:
        r = super().dump()
        r.update(
            {
                "name": "QueryMonkey",
                "failure_count": self.failure_count,
                "success_count": self.success_count,
            }
        )
        return r
