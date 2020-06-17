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
        return {"business": "Idle"}


@dataclass
class JupyterLoginLoop(Business):
    async def run(self) -> None:
        logger = self.monkey.log
        logger.info("Starting up...")

        client = JupyterClient(self.monkey.user, logger)
        await client.hub_login()

        while True:
            await client.ensure_lab()
            await asyncio.sleep(60)
            await client.delete_lab()
            await asyncio.sleep(60)
            logger.info("Next iteration")

    def dump(self) -> dict:
        return {"business": "JupyterLoginLoop"}


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
        return {"business": "JupyterPythonLoop"}
