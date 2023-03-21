"""The monkey."""

from __future__ import annotations

import logging
import sys
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
from typing import Optional

import structlog
from aiohttp import ClientSession
from aiojobs import Scheduler
from aiojobs._job import Job
from safir.datetime import current_datetime, format_datetime_for_logging
from safir.logging import Profile
from safir.slack.blockkit import SlackException, SlackMessage, SlackTextField
from safir.slack.webhook import SlackWebhookClient
from structlog.stdlib import BoundLogger

from ..config import config
from ..models.business.base import BusinessConfig
from ..models.business.empty import EmptyLoopConfig
from ..models.business.jupyterpythonloop import JupyterPythonLoopConfig
from ..models.business.notebookrunner import NotebookRunnerConfig
from ..models.business.tapqueryrunner import TAPQueryRunnerConfig
from ..models.monkey import MonkeyData, MonkeyState
from ..models.user import AuthenticatedUser
from .business.base import Business
from .business.empty import EmptyLoop
from .business.jupyterpythonloop import JupyterPythonLoop
from .business.notebookrunner import NotebookRunner
from .business.tapqueryrunner import TAPQueryRunner

__all__ = ["Monkey"]

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class Monkey:
    """Runs one business and manages its log and configuration."""

    def __init__(
        self,
        *,
        name: str,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
        session: ClientSession,
        logger: BoundLogger,
    ):
        self._name = name
        self._restart = business_config.restart
        self._session = session
        self._user = user

        self._state = MonkeyState.IDLE
        self._logfile = NamedTemporaryFile()
        self._logger = self._build_logger(self._logfile)
        self._global_logger = logger.bind(
            monkey=self._name, user=self._user.username
        )
        self._job: Optional[Job] = None

        # Determine the business class from the type of configuration we got,
        # which in turn will be based on Pydantic validation of the value of
        # the type field.
        self.business: Business
        if isinstance(business_config, EmptyLoopConfig):
            self.business = EmptyLoop(
                business_config.options, user, self._logger
            )
        elif isinstance(business_config, JupyterPythonLoopConfig):
            self.business = JupyterPythonLoop(
                business_config.options, user, self._logger
            )
        elif isinstance(business_config, NotebookRunnerConfig):
            self.business = NotebookRunner(
                business_config.options, user, self._logger
            )
        elif isinstance(business_config, TAPQueryRunnerConfig):
            self.business = TAPQueryRunner(
                business_config.options, user, self._logger
            )
        else:
            msg = f"Unknown business config {business_config}"
            raise RuntimeError(msg)

        self._slack = None
        if config.alert_hook and config.alert_hook != "None":
            self._slack = SlackWebhookClient(
                config.alert_hook, "Mobu", self._global_logger
            )

    async def alert(self, e: Exception) -> None:
        if self._state in (MonkeyState.STOPPING, MonkeyState.FINISHED):
            state = self._state.name
            self._logger.info(f"Not sending alert because state is {state}")
            return
        if not self._slack:
            self._logger.info("Alert hook isn't set, so not sending to Slack")
            return

        if isinstance(e, SlackException):
            # Avoid post_exception here since it adds the application name,
            # but mobu (unusually) uses a dedicated web hook and therefore
            # doesn't need to label its alerts.
            await self._slack.post(e.to_slack())
        else:
            now = current_datetime(microseconds=True)
            date = format_datetime_for_logging(now)
            message = SlackMessage(
                message=f"Unexpected exception {type(e).__name__}: {str(e)}",
                fields=[
                    SlackTextField(heading="Date", text=date),
                    SlackTextField(heading="User", text=self._user.username),
                ],
            )
            await self._slack.post(message)

        self._global_logger.info("Sent alert to Slack")

    def logfile(self) -> str:
        self._logfile.flush()
        return self._logfile.name

    async def start(self, scheduler: Scheduler) -> None:
        self._job = await scheduler.spawn(self._runner())

    async def _runner(self) -> None:
        run = True

        while run:
            try:
                self._state = MonkeyState.RUNNING
                await self.business.run()
                run = False
            except Exception as e:
                msg = "Exception thrown while doing monkey business"
                self._logger.exception(msg)
                await self.alert(e)
                run = self._restart and self._state == MonkeyState.RUNNING
                if run:
                    self._state = MonkeyState.ERROR
                    await self.business.error_idle()
                    if self._state == MonkeyState.STOPPING:
                        run = False
                else:
                    self._state = MonkeyState.STOPPING
                    msg = "Shutting down monkey due to error"
                    self._global_logger.warning(msg)

        await self.business.close()
        self.state = MonkeyState.FINISHED

    async def stop(self) -> None:
        if self._state == MonkeyState.FINISHED:
            return
        elif self._state in (MonkeyState.RUNNING, MonkeyState.ERROR):
            self._state = MonkeyState.STOPPING
            await self.business.stop()
        if self._job:
            await self._job.wait()
        self._state = MonkeyState.FINISHED

    def dump(self) -> MonkeyData:
        return MonkeyData(
            name=self._name,
            business=self.business.dump(),
            state=self._state,
            user=self._user,
        )

    def _build_logger(self, logfile: _TemporaryFileWrapper) -> BoundLogger:
        """Construct a logger for the actions of this monkey.

        This logger will always log to a file, and will log to standard output
        if the logging profile is ``development``.

        Parameters
        ----------
        logfile
            File to which to write the log messages.

        Returns
        -------
        structlog.BoundLogger
            Logger to use for further monkey actions.
        """
        formatter = logging.Formatter(
            fmt="%(asctime)s %(message)s", datefmt=DATE_FORMAT
        )
        fileHandler = logging.FileHandler(logfile.name)
        fileHandler.setFormatter(formatter)
        logger = logging.getLogger("mobu")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(fileHandler)
        logger.propagate = False
        if config.profile == Profile.development:
            streamHandler = logging.StreamHandler(stream=sys.stdout)
            streamHandler.setFormatter(formatter)
            logger.addHandler(streamHandler)
        result = structlog.wrap_logger(logger, wrapper_class=BoundLogger)
        result.info("Starting new file logger", file=logfile.name)
        return result
