"""Base class for executing code in a Nublado notebook."""

from __future__ import annotations

import random
from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Optional, TypeVar

from httpx import AsyncClient
from safir.datetime import current_datetime, format_datetime_for_logging
from safir.slack.blockkit import SlackException
from structlog.stdlib import BoundLogger

from ...exceptions import JupyterSpawnError, JupyterTimeoutError
from ...models.business.nublado import (
    NubladoBusinessData,
    NubladoBusinessOptions,
    RunningImage,
)
from ...models.user import AuthenticatedUser
from ...storage.jupyter import JupyterClient, JupyterLabSession
from .base import Business

T = TypeVar("T", bound="NubladoBusinessOptions")

__all__ = ["NubladoBusiness", "ProgressLogMessage"]

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


class NubladoBusiness(Business, Generic[T], metaclass=ABCMeta):
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
    http_client
        Shared HTTP client for general web access.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: T,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._client = JupyterClient(
            user=user,
            url_prefix=options.url_prefix,
            image_config=options.image,
            logger=logger,
        )
        self._image: Optional[RunningImage] = None
        self._node: Optional[str] = None

    @abstractmethod
    async def execute_code(self, session: JupyterLabSession) -> None:
        """The core of the execution loop.

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

    def annotations(self) -> dict[str, str]:
        """Timer annotations to use.

        Subclasses should override this to add more annotations based on
        current business state.  They should call ``super().annotations()``
        and then add things to the resulting dictionary.
        """
        result = {}
        if self._image and self._image.description:
            result["image"] = self._image.description
        if self._node:
            result["node"] = self._node
        return result

    async def startup(self) -> None:
        if self.options.jitter:
            with self.timings.start("pre_login_delay"):
                max_delay = self.options.jitter
                if not await self.pause(random.uniform(0, max_delay)):
                    return
        await self.hub_login()
        if not await self._client.is_lab_stopped():
            try:
                await self.delete_lab()
            except JupyterTimeoutError:
                msg = "Unable to delete pre-existing lab, continuing anyway"
                self.logger.warning(msg)

    async def execute(self) -> None:
        """The work done in each iteration of the loop."""
        if self.options.delete_lab or await self._client.is_lab_stopped():
            self._image = None
            if not await self.spawn_lab():
                return
        await self.lab_login()
        async with self.open_session() as session:
            await self.execute_code(session)
        if self.options.delete_lab:
            await self.hub_login()
            await self.delete_lab()

    async def execution_idle(self) -> bool:
        """Executed between each unit of work execution.

        This is not used directly by `NubladoBusiness`. It should be called by
        subclasses in `execute_code` in between each block of code that is
        executed.
        """
        with self.timings.start("execution_idle"):
            return await self.pause(self.options.execution_idle_time)

    async def shutdown(self) -> None:
        await self.delete_lab()

    async def idle(self) -> None:
        """The idle pause at the end of each loop."""
        if self.options.jitter:
            self.logger.info("Idling...")
            with self.timings.start("idle"):
                extra_delay = random.uniform(0, self.options.jitter)
                await self.pause(self.options.idle_time + extra_delay)
        else:
            await super().idle()

    async def hub_login(self) -> None:
        self.logger.info("Logging in to hub")
        with self.timings.start("hub_login"):
            await self._client.auth_to_hub()

    async def spawn_lab(self) -> bool:
        with self.timings.start("spawn_lab", self.annotations()) as sw:
            timeout = self.options.spawn_timeout
            await self._client.spawn_lab()

            # Pause before using the progress API, since otherwise it may not
            # have attached to the spawner and will not return a full stream
            # of events.
            if not await self.pause(self.options.spawn_settle_time):
                return False
            timeout -= self.options.spawn_settle_time

            # Watch the progress API until the lab has spawned.
            log_messages = []
            progress = self._client.watch_spawn_progress()
            try:
                async for message in self.iter_with_timeout(progress, timeout):
                    log_messages.append(ProgressLogMessage(message.message))
                    if message.ready:
                        return True
            except TimeoutError:
                log = "\n".join([str(m) for m in log_messages])
                raise JupyterSpawnError(log, self.user.username)
            except SlackException:
                raise
            except Exception as e:
                log = "\n".join([str(m) for m in log_messages])
                user = self.user.username
                raise JupyterSpawnError.from_exception(log, e, user)

            # We only fall through if the spawn failed, timed out, or if we're
            # stopping the business.
            if self.stopping:
                return False
            log = "\n".join([str(m) for m in log_messages])
            if sw.elapsed.total_seconds() > timeout:
                elapsed = round(sw.elapsed.total_seconds())
                msg = f"Lab did not spawn after {elapsed}s"
                raise JupyterTimeoutError(msg, self.user.username, log)
            else:
                raise JupyterSpawnError(log, self.user.username)

    async def lab_login(self) -> None:
        self.logger.info("Logging in to lab")
        with self.timings.start("lab_login", self.annotations()):
            await self._client.auth_to_lab()

    @asynccontextmanager
    async def open_session(
        self, notebook: Optional[str] = None
    ) -> AsyncIterator[JupyterLabSession]:
        self.logger.info("Creating lab session")
        stopwatch = self.timings.start("create_session", self.annotations())
        async with await self._client.open_lab_session(notebook) as session:
            stopwatch.stop()
            with self.timings.start("execute_setup", self.annotations()):
                await self.setup_session(session)
            yield session
            await self.lab_login()
            stopwatch = self.timings.start("delete_sesion", self.annotations())
        stopwatch.stop()
        self._node = None

    async def setup_session(self, session: JupyterLabSession) -> None:
        image_data = await session.run_python(_GET_IMAGE)
        if "\n" in image_data:
            reference, description = image_data.split("\n", 1)
            msg = f"Running on image {reference} ({description})"
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
        if self.options.get_node:
            self._node = await session.run_python(_GET_NODE)
            self.logger.info(f"Running on node {self._node}")
        if self.options.working_directory:
            path = self.options.working_directory
            code = _CHDIR_TEMPLATE.format(wd=path)
            self.logger.info(f"Changing directories to {path}")
            await session.run_python(code)

    async def delete_lab(self) -> None:
        self.logger.info("Deleting lab")
        with self.timings.start("delete_lab", self.annotations()):
            await self._client.stop_lab()
            if self.stopping:
                return

            # If we're not stopping, wait for the lab to actually go away.  If
            # we don't do this, we may try to create a new lab while the old
            # one is still shutting down.
            timeout = self.options.delete_timeout
            start = current_datetime(microseconds=True)
            while not await self._client.is_lab_stopped():
                now = current_datetime(microseconds=True)
                elapsed = round((now - start).total_seconds())
                if elapsed > timeout:
                    if not await self._client.is_lab_stopped(log_running=True):
                        msg = f"Lab not deleted after {elapsed}s"
                        raise JupyterTimeoutError(msg, self.user.username)
                msg = f"Waiting for lab deletion ({elapsed}s elapsed)"
                self.logger.info(msg)
                if not await self.pause(2):
                    return

        self.logger.info("Lab successfully deleted")
        self._image = None

    def dump(self) -> NubladoBusinessData:
        return NubladoBusinessData(image=self._image, **super().dump().dict())
