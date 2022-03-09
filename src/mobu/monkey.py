"""The monkey."""

from __future__ import annotations

import logging
import sys
from tempfile import NamedTemporaryFile
from typing import Optional, Type

import structlog
from aiohttp import ClientSession
from aiojobs import Scheduler
from aiojobs._job import Job

from .business.base import Business
from .config import config
from .exceptions import SlackError
from .models.monkey import MonkeyConfig, MonkeyData, MonkeyState
from .models.user import AuthenticatedUser
from .slack import SlackClient

__all__ = ["Monkey"]

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class Monkey:
    """Runs one business and manages its log and configuration."""

    def __init__(
        self,
        monkey_config: MonkeyConfig,
        business_type: Type[Business],
        user: AuthenticatedUser,
        session: ClientSession,
    ):
        self.config = monkey_config
        self.name = monkey_config.name
        self.state = MonkeyState.IDLE
        self.user = user
        self.restart = monkey_config.restart

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
        logger.propagate = False
        logger.info(f"Starting new file logger {self._logfile.name}")
        self.log = structlog.wrap_logger(logger)

        self._slack = None
        if config.alert_hook and config.alert_hook != "None":
            self._slack = SlackClient(config.alert_hook, session, self.log)

        self.business = business_type(self.log, self.config.options, self.user)

    async def alert(self, e: Exception) -> None:
        if self.state in (MonkeyState.STOPPING, MonkeyState.FINISHED):
            state = self.state.name
            self.log.info(f"Not sending alert because state is {state}")
            return
        if not self._slack:
            self.log.info("Alert hook isn't set, so not sending to Slack")
            return

        if isinstance(e, SlackError):
            await self._slack.alert_from_exception(e)
        else:
            msg = f"Unexpected exception {type(e).__name__}: {str(e)}"
            await self._slack.alert(self.user.username, msg)

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
                run = False
            except Exception as e:
                self.log.exception(
                    "Exception thrown while doing monkey business"
                )
                await self.alert(e)
                run = self.restart and self.state == MonkeyState.RUNNING
                if self.state == MonkeyState.RUNNING:
                    self.state = MonkeyState.ERROR
            if run:
                await self.business.error_idle()
                if self.state == MonkeyState.STOPPING:
                    self.log.info("Shutting down monkey")
                    run = False
            else:
                self.log.info("Shutting down monkey")

        await self.business.close()
        self.state = MonkeyState.FINISHED

    async def stop(self) -> None:
        if self.state == MonkeyState.FINISHED:
            return
        elif self.state in (MonkeyState.RUNNING, MonkeyState.ERROR):
            self.state = MonkeyState.STOPPING
            await self.business.stop()
            if self._job:
                await self._job.wait()
        self.state = MonkeyState.FINISHED

    def dump(self) -> MonkeyData:
        return MonkeyData(
            name=self.name,
            business=self.business.dump(),
            restart=self.restart,
            state=self.state,
            user=self.user,
        )
