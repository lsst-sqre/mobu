"""The monkey."""

__all__ = [
    "Monkey",
]

import asyncio
import logging
import sys
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import IO

import structlog
from aiojobs import Scheduler
from aiojobs._job import Job
from structlog._config import BoundLoggerLazyProxy

from mobu.business import Business
from mobu.user import User


@dataclass
class Monkey:
    user: User
    log: BoundLoggerLazyProxy
    business: Business
    restart: bool
    state: str

    _job: Job
    _logfile: IO[bytes]

    def __init__(self, user: User):
        self.state = "IDLE"
        self.user = user

        self._logfile = NamedTemporaryFile()

        formatter = logging.Formatter(
            fmt="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        fileHandler = logging.FileHandler(self._logfile.name)
        fileHandler.setFormatter(formatter)

        streamHandler = logging.StreamHandler(stream=sys.stdout)
        streamHandler.setFormatter(formatter)

        logger = logging.getLogger(self.user.username)
        logger.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        logger.addHandler(streamHandler)
        logger.info(f"Starting new file logger {self._logfile.name}")
        self.log = structlog.wrap_logger(logger)

    def logfile(self) -> str:
        self._logfile.flush()
        return self._logfile.name

    async def start(self, scheduler: Scheduler) -> None:
        self._job = await scheduler.spawn(self._runner())

    async def _runner(self) -> None:
        run = True
        while run:
            try:
                self.state = "RUNNING"
                await self.business.run()
                self.state = "FINISHED"
            except Exception:
                self.log.exception(
                    "Exception thrown while doing monkey business."
                )
                self.state = "ERROR"
                run = self.restart
                await asyncio.sleep(60)

    async def stop(self) -> None:
        await self._job.close()

    def dump(self) -> dict:
        return {
            "user": self.user.dump(),
            "business": self.business.dump(),
            "state": self.state,
            "restart": self.restart,
        }
