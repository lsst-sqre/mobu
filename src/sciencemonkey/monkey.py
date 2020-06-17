"""The monkey."""

__all__ = [
    "Monkey",
]

import asyncio
import logging
import sys
from dataclasses import dataclass
from tempfile import NamedTemporaryFile

import structlog
from aiojobs import Scheduler
from aiojobs._job import Job
from structlog._config import BoundLoggerLazyProxy

from sciencemonkey.business import Business
from sciencemonkey.user import User


@dataclass
class Monkey:
    user: User
    log: BoundLoggerLazyProxy
    business: Business
    restart: bool

    _job: Job
    _logfile: NamedTemporaryFile

    def __init__(self, user: User):
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
                await self.business.run()
            except Exception:
                self.log.exception(
                    "Exception thrown while doing monkey business."
                )
                await asyncio.sleep(60)
            run = self.restart

    async def stop(self) -> None:
        await self._job.close()

    def dump(self) -> dict:
        return {
            "user": self.user.dump(),
            "business": self.business.dump(),
            "restart": self.restart,
        }
