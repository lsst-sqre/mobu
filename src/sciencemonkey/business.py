"""Business logic for sciencemonkeys."""

__all__ = [
    "Business",
    "JupyterLoginLoop",
    "JupyterPythonLoop",
]

import asyncio
import logging
import sys
from dataclasses import dataclass
from tempfile import NamedTemporaryFile

import structlog
from structlog._config import BoundLoggerLazyProxy

from sciencemonkey.jupyterclient import JupyterClient
from sciencemonkey.user import User


@dataclass
class Business:
    user: User
    _logfile: NamedTemporaryFile

    def __init__(self, user: User):
        self.user = user

    def get_logger(self, name: str) -> BoundLoggerLazyProxy:
        self._logfile = NamedTemporaryFile()
        logger = logging.getLogger(self.user.username)
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.FileHandler(self._logfile.name))
        logger.addHandler(logging.StreamHandler(stream=sys.stdout))
        logger.info(f"Starting new file logger {self._logfile.name}")
        return structlog.wrap_logger(logger)

    def logfile(self) -> str:
        self._logfile.flush()
        return self._logfile.name

    async def run(self) -> None:
        logger = self.get_logger("Idle")

        while True:
            logger.info("Idling...")
            await asyncio.sleep(5)


@dataclass
class JupyterLoginLoop(Business):
    def __init__(self, user: User):
        self.user = user

    async def run(self) -> None:
        logger = self.get_logger("JupyterLoginLoop")
        logger.info("Starting up...")

        client = JupyterClient(self.user, logger)
        await client.hub_login()

        while True:
            await client.ensure_lab()
            await asyncio.sleep(60)
            await client.delete_lab()
            await asyncio.sleep(60)
            logger.info("Next iteration")


@dataclass
class JupyterPythonLoop(Business):
    def __init__(self, user: User):
        self.user = user

    async def run(self) -> None:
        logger = self.get_logger("JupyterPythonLoop")
        logger.info("Starting up...")

        client = JupyterClient(self.user, logger)
        await client.hub_login()
        await client.ensure_lab()

        kernel = await client.create_kernel()

        while True:
            reply = await client.run_python(kernel, "print(2+2)")
            logger.info(reply)
            await asyncio.sleep(60)
