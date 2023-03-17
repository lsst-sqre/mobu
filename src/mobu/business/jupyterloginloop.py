"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from aiohttp import ClientError, ClientResponseError
from safir.datetime import current_datetime, format_datetime_for_logging
from structlog.stdlib import BoundLogger

from ..exceptions import (
    JupyterResponseError,
    JupyterSpawnError,
    JupyterTimeoutError,
)
from ..jupyterclient import JupyterClient
from ..models.business import BusinessConfig, BusinessData
from ..models.jupyter import JupyterImage
from ..models.user import AuthenticatedUser
from .base import Business

__all__ = ["JupyterLoginLoop", "ProgressLogMessage"]


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


class JupyterLoginLoop(Business):
    """Business that logs on to the hub, creates a lab, and deletes it.

    This class modifies the core `~mobu.business.base.Business` loop by
    providing the overall ``execute`` framework and defualt ``startup`` and
    ``shutdown`` methods.  It will log on to JupyterHub, ensure no lab
    currently exists, create a lab, run ``lab_business``, and then shut down
    the lab before starting another iteration.

    Subclasses should override ``lab_business`` to do whatever they want to do
    inside a lab.  The default behavior just waits for ``login_idle_time``.

    Once this business has been stopped, it cannot be started again (the
    `aiohttp.ClientSession` will be closed), and the instance should be
    dropped after retrieving any status information.
    """

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        self.image: Optional[JupyterImage] = None
        self._client = JupyterClient(user, logger, business_config.jupyter)

    async def close(self) -> None:
        await self._client.close()

    def annotations(self) -> dict[str, str]:
        """Timer annotations to use.

        Subclasses should override this to add more annotations based on
        current business state.  They should call ``super().annotations()``
        and then add things to the resulting dictionary.
        """
        return {"image": self.image.name} if self.image else {}

    async def startup(self) -> None:
        await self.hub_login()
        if not await self._client.is_lab_stopped():
            try:
                await self.delete_lab()
            except JupyterTimeoutError:
                msg = "Unable to delete pre-existing lab, continuing anyway"
                self.logger.warning(msg)

    async def execute(self) -> None:
        """The work done in each iteration of the loop."""
        if self.config.delete_lab or await self._client.is_lab_stopped():
            self.image = None
            await self.spawn_lab()
            if self.stopping:
                return
            await self.lab_settle()
            if self.stopping:
                return  # type: ignore[unreachable]  # bug in mypy 0.930
        await self.lab_login()
        await self.lab_business()
        if self.config.delete_lab:
            await self.hub_login()
            await self.delete_lab()

    async def shutdown(self) -> None:
        await self.delete_lab()

    async def hub_login(self) -> None:
        self.logger.info("Logging in to hub")
        with self.timings.start("hub_login"):
            await self._client.hub_login()

    async def spawn_lab(self) -> None:
        with self.timings.start("spawn_lab", self.annotations()) as sw:
            self.image = await self._client.spawn_lab()

            # Pause before using the progress API, since otherwise it may not
            # have attached to the spawner and will not return a full stream
            # of events.  (It will definitely take longer than 5s for the lab
            # to spawn.)
            await self.pause(self.config.spawn_settle_time)
            if self.stopping:
                return

            # Watch the progress API until the lab has spawned.
            log_messages = []
            timeout = self.config.spawn_timeout - self.config.spawn_settle_time
            progress = self._client.spawn_progress()
            try:
                async for message in self.iter_with_timeout(progress, timeout):
                    log_messages.append(ProgressLogMessage(message.message))
                    if message.ready:
                        return
            except ClientResponseError as e:
                username = self.user.username
                raise JupyterResponseError.from_exception(username, e) from e
            except (
                ClientError,
                ConnectionResetError,
                asyncio.TimeoutError,
            ) as e:
                username = self.user.username
                log = "\n".join([str(m) for m in log_messages])
                raise JupyterSpawnError.from_exception(username, log, e) from e

            # We only fall through if the spawn failed, timed out, or if we're
            # stopping the business.
            if self.stopping:
                return  # type: ignore[unreachable]  # bug in mypy 0.930
            log = "\n".join([str(m) for m in log_messages])
            if sw.elapsed.total_seconds() > timeout:
                elapsed = round(sw.elapsed.total_seconds())
                msg = f"Lab did not spawn after {elapsed}s"
                raise JupyterTimeoutError(self.user.username, msg, log)
            else:
                raise JupyterSpawnError(self.user.username, log)

    async def lab_settle(self) -> None:
        with self.timings.start("lab_settle"):
            await self.pause(self.config.lab_settle_time)

    async def lab_login(self) -> None:
        with self.timings.start("lab_login", self.annotations()):
            await self._client.lab_login()

    async def delete_lab(self) -> None:
        self.logger.info("Deleting lab")
        with self.timings.start("delete_lab", self.annotations()):
            await self._client.delete_lab()

            # If we're not stopping, wait for the lab to actually go away.  If
            # we don't do this, we may try to create a new lab while the old
            # one is still shutting down.
            if self.stopping:
                return
            timeout = self.config.delete_timeout
            start = current_datetime(microseconds=True)
            while not await self._client.is_lab_stopped():
                now = current_datetime(microseconds=True)
                elapsed = round((now - start).total_seconds())
                if elapsed > timeout:
                    if not await self._client.is_lab_stopped(final=True):
                        msg = f"Lab not deleted after {elapsed}s"
                        raise JupyterTimeoutError(self.user.username, msg)
                msg = f"Waiting for lab deletion ({elapsed}s elapsed)"
                self.logger.info(msg)
                await self.pause(2)
                if self.stopping:
                    return  # type: ignore[unreachable]  # bug in mypy 0.930

        self.logger.info("Lab successfully deleted")
        self.image = None

    async def lab_business(self) -> None:
        """Do whatever business we want to do inside a lab.

        Placeholder function intended to be overridden by subclasses.  The
        default behavior is to wait a minute and then shut the lab down
        again.
        """
        with self.timings.start("lab_wait"):
            await self.pause(self.config.login_idle_time)

    def dump(self) -> BusinessData:
        data = super().dump()
        data.image = self.image if self.image else None
        return data
