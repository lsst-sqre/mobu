"""Base class for executing code in a Nublado notebook."""

from __future__ import annotations

import re
from abc import ABCMeta, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from random import SystemRandom
from typing import Any

import sentry_sdk
from rubin.nublado.client import JupyterLabSession, NubladoClient
from safir.datetime import current_datetime, format_datetime_for_logging
from safir.sentry import duration
from sentry_sdk import set_tag
from sentry_sdk.tracing import Span
from structlog.stdlib import BoundLogger

from ...dependencies.config import config_dependency
from ...events import Events, NubladoDeleteLab, NubladoSpawnLab
from ...exceptions import (
    JupyterDeleteTimeoutError,
    JupyterSpawnError,
    JupyterSpawnTimeoutError,
)
from ...models.business.nublado import (
    NubladoBusinessData,
    NubladoBusinessOptions,
    RunningImage,
)
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from .base import Business

__all__ = ["NubladoBusiness", "ProgressLogMessage"]

_ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
"""Regex that matches ANSI escape sequences."""

_CHDIR_TEMPLATE = 'import os; os.chdir("{wd}")'
"""Template to construct the code to run to set the working directory."""

_GET_IMAGE = """
import os
print(
    os.getenv("JUPYTER_IMAGE_SPEC"),
    os.getenv("IMAGE_DESCRIPTION"),
    sep="\\n",
)
"""
"""Code to get information about the lab image."""

_GET_NODE = """
from lsst.rsp import get_node
print(get_node(), end="")
"""
"""Code to get the node on which the lab is running."""


@dataclass(frozen=True)
class ProgressLogMessage:
    """A single log message with timestamp from spawn progress."""

    message: str
    """The message."""

    timestamp: datetime = field(
        default_factory=lambda: current_datetime(microseconds=True)
    )
    """When the event was received."""

    def __str__(self) -> str:
        timestamp = format_datetime_for_logging(self.timestamp)
        return f"{timestamp} - {self.message}"


class NubladoBusiness[T: NubladoBusinessOptions](
    Business[T], metaclass=ABCMeta
):
    """Base class for business that executes Python code in a Nublado notebook.

    This class modifies the core `~mobu.business.base.Business` loop by
    providing `startup`, `execute`, and `shutdown` methods. It will log on to
    JupyterHub, ensure no lab currently exists, create a lab, call
    `execute_code`, and then optionally shut down the lab before starting
    another iteration.

    Subclasses must override `execute_code` to do whatever they want to do
    inside a lab.

    Once this business has been stopped, it cannot be started again (the
    `aiohttp.ClientSession` will be closed), and the instance should be
    dropped after retrieving any wanted status information.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    events
        Event publishers.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        *,
        options: T,
        user: AuthenticatedUser,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            events=events,
            logger=logger,
            flock=flock,
        )

        config = config_dependency.config
        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        environment_url = str(config.environment_url).rstrip("/")
        self._client = NubladoClient(
            user=user.to_client_user(),
            base_url=environment_url + options.url_prefix,
            logger=logger,
            timeout=options.jupyter_timeout,
        )
        self._image: RunningImage | None = None
        self._node: str | None = None
        self._random = SystemRandom()

        # We want multiple transactions for each call to execute (one for each
        # notebook in a NotebookRunner business, for example)
        self.execute_transaction = False

    @abstractmethod
    async def execute_code(self, session: JupyterLabSession) -> None:
        """Execute some code inside the Jupyter lab.

        Must be overridden by subclasses to use the provided lab session to
        perform whatever operations are desired inside the lab. If multiple
        blocks of code are being executed, call `execution_idle` between each
        one.

        Parameters
        ----------
        session
            Authenticated session to the Nublado lab.
        """

    async def close(self) -> None:
        await self._client.close()

    async def startup(self) -> None:
        # We need to start a span around this transaction becaues if we don't,
        # the nested transaction shows up as "No instrumentation" in the
        # enclosing transaction in the Sentry UI.
        if self.options.jitter:
            with capturing_start_span(op="pre_login_delay"):
                max_delay = self.options.jitter.total_seconds()
                delay = self._random.uniform(0, max_delay)
                if not await self.pause(timedelta(seconds=delay)):
                    return
        await self.hub_login()
        if not await self._client.is_lab_stopped():
            try:
                await self.delete_lab()
            except JupyterDeleteTimeoutError:
                msg = "Unable to delete pre-existing lab, continuing anyway"
                self.logger.warning(msg)

    async def execute(self) -> None:
        with start_transaction(
            name=f"{self.name} - pre execute code",
            op=f"mobu.{self.name}.pre_execute_code",
        ):
            if self.options.delete_lab or await self._client.is_lab_stopped():
                self._image = None
                set_tag("image_description", None)
                set_tag("image_reference", None)
                if not await self.spawn_lab():
                    return
            await self.lab_login()
        async with self.open_session() as session:
            await self.execute_code(session)
        with start_transaction(
            name=f"{self.name} - post execute code",
            op=f"mobu.{self.name}.post_execute_code",
        ):
            if self.options.delete_lab:
                await self.hub_login()
                await self.delete_lab()

    async def execution_idle(self) -> bool:
        """Pause between each unit of work execution.

        This is not used directly by `NubladoBusiness`. It should be called by
        subclasses in `execute_code` in between each block of code that is
        executed.
        """
        with capturing_start_span(op="execution_idle"):
            return await self.pause(self.options.execution_idle_time)

    async def shutdown(self) -> None:
        await self.hub_login()
        await self.delete_lab()

    async def idle(self) -> None:
        if self.options.jitter:
            self.logger.info("Idling...")
            jitter = self.options.jitter.total_seconds()
            delay_seconds = self._random.uniform(0, jitter)
            delay = timedelta(seconds=delay_seconds)
            with capturing_start_span(op="idle"):
                await self.pause(self.options.idle_time + delay)
        else:
            await super().idle()

    async def hub_login(self) -> None:
        self.logger.info("Logging in to hub")
        with capturing_start_span(op="hub_login"):
            await self._client.auth_to_hub()

    async def spawn_lab(self) -> bool:
        with capturing_start_span(op="spawn_lab") as span:
            try:
                result = await self._spawn_lab(span)
            except:
                await self.events.nublado_spawn_lab.publish(
                    NubladoSpawnLab(
                        success=False,
                        duration=duration(span),
                        **self.common_event_attrs(),
                    )
                )
                raise
        await self.events.nublado_spawn_lab.publish(
            NubladoSpawnLab(
                success=True,
                duration=duration(span),
                **self.common_event_attrs(),
            )
        )
        return result

    async def _spawn_lab(self, span: Span) -> bool:
        timeout = self.options.spawn_timeout
        await self._client.spawn_lab(self.options.image)

        # Pause before using the progress API, since otherwise it may not
        # have attached to the spawner and will not return a full stream
        # of events.
        if not await self.pause(self.options.spawn_settle_time):
            return False
        timeout -= self.options.spawn_settle_time

        # Watch the progress API until the lab has spawned.
        log_messages = []
        progress = self._client.watch_spawn_progress()
        progress_generator = self.iter_with_timeout(progress, timeout)
        async with aclosing(progress_generator):
            try:
                async for message in progress_generator:
                    log_messages.append(ProgressLogMessage(message.message))
                    if message.ready:
                        return True
            except:
                log = "\n".join([str(m) for m in log_messages])
                sentry_sdk.get_current_scope().add_attachment(
                    filename="spawn_log.txt",
                    bytes=self.remove_ansi_escapes(log).encode(),
                )
                raise

        # We only fall through if the spawn failed, timed out, or if we're
        # stopping the business.
        if self.stopping:
            return False
        log = "\n".join([str(m) for m in log_messages])
        sentry_sdk.get_current_scope().add_attachment(
            filename="spawn_log.txt",
            bytes=self.remove_ansi_escapes(log).encode(),
        )
        spawn_duration = duration(span)
        if spawn_duration > timeout:
            elapsed_seconds = round(spawn_duration.total_seconds())
            msg = f"Lab did not spawn after {elapsed_seconds}s"
            raise JupyterSpawnTimeoutError(msg)
        raise JupyterSpawnError

    async def lab_login(self) -> None:
        self.logger.info("Logging in to lab")
        with capturing_start_span(op="lab_login"):
            await self._client.auth_to_lab()

    @asynccontextmanager
    async def open_session(
        self, notebook: str | None = None
    ) -> AsyncGenerator[JupyterLabSession]:
        self.logger.info("Creating lab session")
        opts: dict[str, Any] = {
            "max_websocket_size": self.options.max_websocket_message_size
        }
        create_session_cm = capturing_start_span(op="create_session")
        create_session_cm.__enter__()
        async with self._client.open_lab_session(notebook, **opts) as session:
            create_session_cm.__exit__(None, None, None)
            with capturing_start_span(op="execute_setup"):
                await self.setup_session(session)
            yield session
            await self.lab_login()
            self.logger.info("Deleting lab session")
            delete_session_cm = capturing_start_span(op="delete_session")
            delete_session_cm.__enter__()
        delete_session_cm.__exit__(None, None, None)
        self._node = None
        set_tag("node", None)

    async def setup_session(self, session: JupyterLabSession) -> None:
        image_data = await session.run_python(_GET_IMAGE)
        if "\n" in image_data:
            reference, description = image_data.split("\n", 1)
            msg = f"Running on image {reference} ({description.strip()})"
            self.logger.info(msg)
        else:
            msg = "Unable to get running image from reply"
            self.logger.warning(msg, image_data=image_data)
            reference = None
            description = None
        self._image = RunningImage(
            reference=reference.strip() if reference else None,
            description=description.strip() if description else None,
        )
        set_tag("image_description", self._image.description)
        set_tag("image_reference", self._image.reference)
        if self.options.get_node:
            self._node = await session.run_python(_GET_NODE)
            set_tag("node", self._node)
            self.logger.info(f"Running on node {self._node}")
        if self.options.working_directory:
            path = self.options.working_directory
            code = _CHDIR_TEMPLATE.format(wd=path)
            self.logger.info(f"Changing directories to {path}")
            await session.run_python(code)

    async def delete_lab(self) -> None:
        with capturing_start_span(op="delete_lab") as span:
            try:
                result = await self._delete_lab()
            except:
                await self.events.nublado_delete_lab.publish(
                    NubladoDeleteLab(
                        success=False,
                        duration=duration(span),
                        **self.common_event_attrs(),
                    )
                )
                raise
        if result:
            # Only record a success if we waited to see if the delete was
            # actually successful.
            await self.events.nublado_delete_lab.publish(
                NubladoDeleteLab(
                    success=True,
                    duration=duration(span),
                    **self.common_event_attrs(),
                )
            )

    async def _delete_lab(self) -> bool:
        """Delete a lab.

        Returns
        -------
        bool
            True if we know the lab was successfully deleted, False if we
            didn't wait to find out if the lab was successfully deleted.
        """
        self.logger.info("Deleting lab")
        await self._client.stop_lab()
        if self.stopping:
            return False

        # If we're not stopping, wait for the lab to actually go away.  If
        # we don't do this, we may try to create a new lab while the old
        # one is still shutting down.
        start = current_datetime(microseconds=True)
        while not await self._client.is_lab_stopped():
            elapsed = current_datetime(microseconds=True) - start
            elapsed_seconds = round(elapsed.total_seconds())
            if elapsed > self.options.delete_timeout:
                if not await self._client.is_lab_stopped(log_running=True):
                    msg = f"Lab not deleted after {elapsed_seconds}s"
                    raise JupyterDeleteTimeoutError(msg)
            msg = f"Waiting for lab deletion ({elapsed_seconds}s elapsed)"
            self.logger.info(msg)
            if not await self.pause(timedelta(seconds=2)):
                return False

        self.logger.info("Lab successfully deleted")
        self._image = None
        set_tag("image_description", None)
        set_tag("image_reference", None)
        return True

    def dump(self) -> NubladoBusinessData:
        return NubladoBusinessData(
            image=self._image, **super().dump().model_dump()
        )

    def remove_ansi_escapes(self, string: str) -> str:
        """Remove ANSI escape sequences from a string.

        Jupyter labs like to format error messages with lots of ANSI
        escape sequences, and Slack doesn't like that in messages (nor do
        humans want to see them). Strip them out.

        Based on `this StackOverflow answer
        <https://stackoverflow.com/questions/14693701/>`__.

        Parameters
        ----------
        string
            String to strip ANSI escapes from.

        Returns
        -------
        str
            Sanitized string.
        """
        return _ANSI_REGEX.sub("", string)
