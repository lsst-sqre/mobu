"""Behaviors for sciencemonkey users."""

__all__ = [
    "Idle",
]

import asyncio
from dataclasses import dataclass

import structlog

from sciencemonkey.jupyterclient import JupyterClient
from sciencemonkey.user import User

logger = structlog.get_logger(__name__)


@dataclass
class Idle:
    user: User

    async def run(self) -> None:
        while True:
            logger.info("Idling...")
            await asyncio.sleep(5)


@dataclass
class JupyterLoginLoop:
    user: User

    async def run(self) -> None:
        logger.info("Starting JupyterLoginLoop")

        client = JupyterClient(self.user)
        await client.hub_login()

        while True:
            await client.ensure_lab()
            await asyncio.sleep(60)
            await client.delete_lab()
            await asyncio.sleep(60)


@dataclass
class JupyterPythonLoop:
    user: User

    async def run(self) -> None:
        logger.info("Starting JupyterPythonLoop")

        client = JupyterClient(self.user)
        await client.hub_login()
        await client.ensure_lab()

        kernel = await client.create_kernel()

        while True:
            reply = await client.run_python(kernel, "print(2+2)")
            logger.info(reply)
            await asyncio.sleep(60)
