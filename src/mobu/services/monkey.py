"""The monkey."""

from __future__ import annotations

import logging
import sys
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper

import structlog
from aiojobs import Job, Scheduler
from httpx import AsyncClient
from safir.datetime import current_datetime, format_datetime_for_logging
from safir.logging import Profile
from safir.slack.blockkit import SlackException, SlackMessage, SlackTextField
from safir.slack.webhook import SlackWebhookClient
from structlog.stdlib import BoundLogger

from ..config import config
from ..exceptions import MobuSlackException
from ..models.business.base import BusinessConfig
from ..models.business.empty import EmptyLoopConfig
from ..models.business.gitlfs import GitLFSConfig
from ..models.business.notebookrunner import NotebookRunnerConfig
from ..models.business.nubladopythonloop import NubladoPythonLoopConfig
from ..models.business.tapqueryrunner import TAPQueryRunnerConfig
from ..models.business.tapquerysetrunner import TAPQuerySetRunnerConfig
from ..models.monkey import MonkeyData, MonkeyState
from ..models.user import AuthenticatedUser
from .business.base import Business
from .business.empty import EmptyLoop
from .business.gitlfs import GitLFSBusiness
from .business.notebookrunner import NotebookRunner
from .business.nubladopythonloop import NubladoPythonLoop
from .business.tapqueryrunner import TAPQueryRunner
from .business.tapquerysetrunner import TAPQuerySetRunner

__all__ = ["Monkey"]

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class Monkey:
    """Runs one business and manages its log and configuration.

    Parameters
    ----------
    name
        Name of this monkey.
    flock
        Name of the flock this monkey belongs to, or `None` if it is running
        as a solitary.
    business_config
        Configuration for the business it should run.
    user
        User the monkey should run as.
    http_client
        Shared HTTP client.
    logger
        Global logger.
    """

    def __init__(
        self,
        *,
        name: str,
        flock: str | None = None,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        self._name = name
        self._flock = flock
        self._restart = business_config.restart
        self._log_level = business_config.options.log_level
        self._http_client = http_client
        self._user = user

        self._state = MonkeyState.IDLE
        self._logfile = NamedTemporaryFile()
        self._logger = self._build_logger(self._logfile)
        self._global_logger = logger.bind(
            monkey=self._name, user=self._user.username
        )
        self._job: Job | None = None

        # Determine the business class from the type of configuration we got,
        # which in turn will be based on Pydantic validation of the value of
        # the type field.
        self.business: Business
        if isinstance(business_config, EmptyLoopConfig):
            self.business = EmptyLoop(
                business_config.options, user, self._http_client, self._logger
            )
        elif isinstance(business_config, GitLFSConfig):
            self.business = GitLFSBusiness(
                business_config.options, user, self._http_client, self._logger
            )
        elif isinstance(business_config, NubladoPythonLoopConfig):
            self.business = NubladoPythonLoop(
                business_config.options, user, self._http_client, self._logger
            )
        elif isinstance(business_config, NotebookRunnerConfig):
            self.business = NotebookRunner(
                business_config.options, user, self._http_client, self._logger
            )
        elif isinstance(business_config, TAPQueryRunnerConfig):
            self.business = TAPQueryRunner(
                business_config.options, user, self._http_client, self._logger
            )
        elif isinstance(business_config, TAPQuerySetRunnerConfig):
            self.business = TAPQuerySetRunner(
                business_config.options, user, self._http_client, self._logger
            )
        else:
            msg = f"Unknown business config {business_config}"
            raise TypeError(msg)

        self._slack = None
        if config.alert_hook:
            self._slack = SlackWebhookClient(
                str(config.alert_hook), "Mobu", self._global_logger
            )

    async def alert(self, exc: Exception) -> None:
        """Send an alert to Slack.

        Parameters
        ----------
        exc
            Exception prompting the alert.
        """
        if self._state in (MonkeyState.STOPPING, MonkeyState.FINISHED):
            state = self._state.name
            self._logger.info(f"Not sending alert because state is {state}")
            return
        if not self._slack:
            self._logger.info("Alert hook isn't set, so not sending to Slack")
            return

        if isinstance(exc, SlackException):
            # Avoid post_exception here since it adds the application name,
            # but mobu (unusually) uses a dedicated web hook and therefore
            # doesn't need to label its alerts.
            await self._slack.post(exc.to_slack())
        else:
            now = current_datetime(microseconds=True)
            date = format_datetime_for_logging(now)
            name = type(exc).__name__
            error = f"{name}: {exc!s}"
            if self._flock:
                monkey = f"{self._flock}/{self._name}"
            else:
                monkey = self._name
            message = SlackMessage(
                message=f"Unexpected exception {error}",
                fields=[
                    SlackTextField(heading="Exception type", text=name),
                    SlackTextField(heading="Failed at", text=date),
                    SlackTextField(heading="Monkey", text=monkey),
                    SlackTextField(heading="User", text=self._user.username),
                ],
            )
            await self._slack.post(message)

        self._global_logger.info("Sent alert to Slack")

    def logfile(self) -> str:
        """Get the log file for a monkey's log."""
        self._logfile.flush()
        return self._logfile.name

    async def run_once(self) -> str | None:
        """Run the monkey business once.

        Returns
        -------
        str or None
            Error message on failure, or `None` if the business succeeded.
        """
        self._state = MonkeyState.RUNNING
        error = None
        try:
            await self.business.run_once()
            self._state = MonkeyState.FINISHED
        except Exception as e:
            msg = "Exception thrown while doing monkey business"
            self._logger.exception(msg)
            error = str(e)
            self._state = MonkeyState.ERROR
        return error

    async def start(self, scheduler: Scheduler) -> None:
        """Start the monkey."""
        self._job = await scheduler.spawn(self._runner())

    async def _runner(self) -> None:
        """Core monkey execution loop.

        This is the top-level function that represents a running monkey. It
        executes the business, catches exceptions, reports them, and restarts
        or exits as intended.
        """
        run = True

        while run:
            try:
                self._state = MonkeyState.RUNNING
                await self.business.run()
                run = False
            except Exception as e:
                msg = "Exception thrown while doing monkey business"
                if isinstance(e, MobuSlackException):
                    if self._flock:
                        e.monkey = f"{self._flock}/{self._name}"
                    else:
                        e.monkey = self._name
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
        """Stop the monkey."""
        if self._state in (MonkeyState.RUNNING, MonkeyState.ERROR):
            self._state = MonkeyState.STOPPING
            await self.business.stop()
        if self._job:
            await self._job.wait()
            self._job = None
        self._state = MonkeyState.FINISHED

    def signal_refresh(self) -> None:
        """Tell the business to refresh."""
        self.business.signal_refresh()

    def dump(self) -> MonkeyData:
        """Return information about a running monkey."""
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
        file_handler = logging.FileHandler(logfile.name)
        file_handler.setFormatter(formatter)
        logger = logging.getLogger(self._name)
        logger.handlers = []
        logger.setLevel(self._log_level.value)
        logger.addHandler(file_handler)
        logger.propagate = False
        if config.profile == Profile.development:
            stream_handler = logging.StreamHandler(stream=sys.stdout)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        result = structlog.wrap_logger(logger, wrapper_class=BoundLogger)
        result.info("Starting new file logger", file=logfile.name)
        return result
