"""Business logic for sciencemonkeys."""

__all__ = [
    "Business",
    "JupyterLoginLoop",
    "JupyterPythonLoop",
]

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sciencemonkey.jupyterclient import JupyterClient

if TYPE_CHECKING:
    from sciencemonkey.monkey import Monkey


@dataclass
class Business:
    monkey: "Monkey"

    async def run(self) -> None:
        logger = self.monkey.log

        while True:
            logger.info("Idling...")
            await asyncio.sleep(5)

    def dump(self) -> dict:
        return {"name": "Idle"}


@dataclass
class JupyterLoginLoop(Business):
    success_count: int = 0
    failure_count: int = 0

    async def run(self) -> None:
        try:
            logger = self.monkey.log
            logger.info("Starting up...")

            client = JupyterClient(self.monkey.user, logger)
            await client.hub_login()
            logger.info("Logged into hub")

            while True:
                logger.info("Starting next iteration")
                await client.ensure_lab()
                logger.info("Lab created.")
                await asyncio.sleep(60)
                logger.info("Deleting lab.")
                await client.delete_lab()
                self.success_count += 1
                logger.info("Lab successfully deleted.")
                await asyncio.sleep(60)
        finally:
            self.failure_count += 1

    def dump(self) -> dict:
        return {
            "name": "JupyterLoginLoop",
            "failure_count": self.failure_count,
            "success_count": self.success_count,
        }


@dataclass
class JupyterPythonLoop(Business):
    async def run(self) -> None:
        logger = self.monkey.log
        logger.info("Starting up...")

        client = JupyterClient(self.monkey.user, logger)
        await client.hub_login()
        await client.ensure_lab()

        kernel = await client.create_kernel()

        while True:
            reply = await client.run_python(kernel, "print(2+2)")
            logger.info(reply)
            await asyncio.sleep(60)

    def dump(self) -> dict:
        return {"name": "JupyterPythonLoop"}
