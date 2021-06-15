"""The monkey."""

__all__ = [
    "Monkey",
]

import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import IO, Any, Dict

import structlog
from aiohttp import ClientSession
from aiojobs import Scheduler
from aiojobs._job import Job
from structlog._config import BoundLoggerLazyProxy

from mobu.business import Business
from mobu.config import Configuration
from mobu.user import User

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class Monkey:
    name: str
    user: User
    log: BoundLoggerLazyProxy
    business: Business
    restart: bool
    state: str

    _job: Job
    _logfile: IO[bytes]

    def __init__(self, name: str, user: User, options: Dict[str, Any]):
        self.name = name
        self.state = "IDLE"
        self.user = user
        self.restart = options.get("restart", False)

        self._logfile = NamedTemporaryFile()

        formatter = logging.Formatter(
            fmt="%(asctime)s %(message)s", datefmt=DATE_FORMAT
        )

        fileHandler = logging.FileHandler(self._logfile.name)
        fileHandler.setFormatter(formatter)

        streamHandler = logging.StreamHandler(stream=sys.stdout)
        streamHandler.setFormatter(formatter)

        logger = logging.getLogger(self.name)
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        logger.addHandler(streamHandler)
        logger.info(f"Starting new file logger {self._logfile.name}")
        self.log = structlog.wrap_logger(logger)

    async def alert(self, msg: str) -> None:
        try:
            time = datetime.now().strftime(DATE_FORMAT)
            alert_msg = f"{time} {self.name} {msg}"
            self.log.error(f"Slack Alert: {alert_msg}")
            if Configuration.alert_hook == "None":
                self.log.info("Alert hook isn't set, so not sending to slack.")
                return

            async with ClientSession() as s:
                async with s.post(
                    Configuration.alert_hook, json={"text": alert_msg}
                ) as r:
                    if r.status != 200:
                        self.log.error(
                            f"Error {r.status} trying to send alert to slack"
                        )
        except Exception:
            self.log.exception("Exception thrown while trying to alert!")

    def assign_business(self, business: Business) -> None:
        self.business = business
        business.monkey = self

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
            except asyncio.CancelledError:
                self.log.info("Shutting down")
                run = False
                await self.business.stop()
            except Exception as e:
                self.state = "ERROR"
                self.log.exception(
                    "Exception thrown while doing monkey business."
                )
                # Just pass the exception message - the callstack will
                # be logged but will probably be too spammy to report.
                await self.alert(str(e))
                run = self.restart
                await asyncio.sleep(60)

    async def stop(self) -> None:
        # If we have a delete_lab method in our business's client, use it.
        # The base Business class doesn't have a _client, and the

        await self.business.stop()
        try:
            await self._job.close(timeout=0)
        except asyncio.TimeoutError:
            # Close will normally wait for a timeout to occur before
            # throwing a timeout exception, but we'll just shut it down
            # right away and eat the exception.
            pass

    def dump(self) -> dict:
        return {
            "user": self.user.dump(),
            "business": self.business.dump(),
            "state": self.state,
            "restart": self.restart,
        }
