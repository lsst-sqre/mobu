import asyncio
import os
import random
import time

import jinja2
import pyvo

from mobu.business import Business
from mobu.config import Configuration


def limit_dec(x):
    return max(min(x, 90), -90)


def generate_parameters():
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

    async def run(self) -> None:
        try:
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

            service = pyvo.dal.TAPService(
                Configuration.environment_url + "/api/tap"
            )

            while True:
                template_name = random.choice(env.list_templates())
                template = env.get_template(template_name)
                query = template.render(generate_parameters())
                logger.info("Running: %s", query)
                start = time.time()
                service.search(query)
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
