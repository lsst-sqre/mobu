"""The monkey."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from enum import Enum, auto
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

import structlog
from aiohttp import ClientSession
from aiojobs import Scheduler
from aiojobs._job import Job

from .config import config

if TYPE_CHECKING:
    from typing import Any, Dict, Optional, Type

    from .business.base import Business
    from .user import User

__all__ = ["Monkey"]

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class MonkeyState(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()
    FINISHED = auto()
    ERROR = auto()


class Monkey:
    """Runs one business and manages its log and configuration."""

    def __init__(
        self,
        name: str,
        user: User,
        business: Type[Business],
        options: Dict[str, Any],
        session: ClientSession,
    ):
        self.name = name
        self.state = MonkeyState.IDLE
        self.user = user
        self.restart = options.get("restart", False)

        self._session = session
        self._logfile = NamedTemporaryFile()
        self._job: Optional[Job] = None

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

        self.business = business(self.log, options, self.user)

    async def alert(self, msg: str) -> None:
        if self.state in (MonkeyState.STOPPING, MonkeyState.FINISHED):
            state = self.state.name
            msg = f"Not sending alert '{msg}' because state is {state}"
            self.log.info(msg)
            return

        time = datetime.now().strftime(DATE_FORMAT)
        alert_msg = f"{time} {self.name} {msg}"
        self.log.error(f"Slack Alert: {alert_msg}")
        if config.alert_hook == "None":
            self.log.info("Alert hook isn't set, so not sending to slack.")
            return

        try:
            alert = {"text": alert_msg}
            r = await self._session.post(config.alert_hook, json=alert)
            if r.status != 200:
                msg = f"Error {r.status} trying to send alert to slack"
                self.log.error(msg)
        except Exception:
            self.log.exception("Exception thrown while trying to alert!")

    def logfile(self) -> str:
        self._logfile.flush()
        return self._logfile.name

    async def start(self, scheduler: Scheduler) -> None:
        self._job = await scheduler.spawn(self._runner())

    async def _runner(self) -> None:
        run = True
        while run:
            try:
                self.state = MonkeyState.RUNNING
                await self.business.run()
                self.state = MonkeyState.FINISHED
            except asyncio.CancelledError:
                self.state = MonkeyState.STOPPING
                self.log.info("Shutting down")
                run = False
                await self.business.stop()
                self.state = MonkeyState.FINISHED
            except Exception as e:
                self.state = MonkeyState.ERROR
                self.log.exception(
                    "Exception thrown while doing monkey business."
                )
                # Just pass the exception message - the callstack will
                # be logged but will probably be too spammy to report.
                await self.alert(str(e))
                run = self.restart
                await asyncio.sleep(60)

    async def stop(self) -> None:
        if self.state == MonkeyState.FINISHED:
            return
        self.state = MonkeyState.STOPPING
        await self.business.stop()
        if self._job:
            try:
                await self._job.close(timeout=0)
            except asyncio.TimeoutError:
                # Close will normally wait for a timeout to occur before
                # throwing a timeout exception, but we'll just shut it down
                # right away and eat the exception.
                pass
        self.state = MonkeyState.FINISHED

    def dump(self) -> dict:
        return {
            "user": self.user.dump(),
            "business": self.business.dump(),
            "state": self.state.name,
            "restart": self.restart,
        }
