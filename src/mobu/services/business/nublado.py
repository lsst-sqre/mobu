"""Base class for executing code in a Nublado notebook."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from random import SystemRandom
from typing import Generic, TypeVar

import rubin.nublado.client.exceptions as ne
from httpx import AsyncClient
from rubin.nublado.client import JupyterLabSession, NubladoClient
from safir.datetime import current_datetime, format_datetime_for_logging
from safir.slack.blockkit import SlackException
from structlog.stdlib import BoundLogger

from ...dependencies.config import config_dependency
from ...events import Events, NubladoDeleteLab, NubladoSpawnLab
from ...exceptions import (
    CodeExecutionError,
    JupyterProtocolError,
    JupyterSpawnError,
    JupyterTimeoutError,
    JupyterWebError,
)
from ...models.business.nublado import (
    NubladoBusinessData,
    NubladoBusinessOptions,
    RunningImage,
)
from ...models.user import AuthenticatedUser
from ...services.timings import Stopwatch
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
        http_client: AsyncClient,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            http_client=http_client,
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

    def annotations(self) -> dict[str, str]:
        """Timer annotations to use.

        Subclasses should override this to add more annotations based on
        current business state.  They should call ``super().annotations()``
        and then add things to the resulting dictionary.
        """
        result = {}
        if self._image:
            result["image"] = (
                self._image.description
                or self._image.reference
                or "<image unknown>"
            )
        if self._node:
            result["node"] = self._node
        return result

    async def startup(self) -> None:
        if self.options.jitter:
            with self.timings.start("pre_login_delay"):
                max_delay = self.options.jitter.total_seconds()
                delay = self._random.uniform(0, max_delay)
                if not await self.pause(timedelta(seconds=delay)):
                    return
        await self.hub_login()
        if not await self._client.is_lab_stopped():
            try:
                await self.delete_lab()
            except JupyterTimeoutError:
                msg = "Unable to delete pre-existing lab, continuing anyway"
                self.logger.warning(msg)

    async def execute(self) -> None:
        try:
            await self._execute()
        except Exception as exc:
            monkey = getattr(exc, "monkey", None)
            event = getattr(exc, "event", "execute_code")
            if isinstance(exc, ne.CodeExecutionError):
                raise CodeExecutionError.from_client_exception(
                    exc,
                    monkey=monkey,
                    event=event,
                    annotations=self.annotations(),
                ) from exc
            raise

    async def _execute(self) -> None:
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
        """Pause between each unit of work execution.

        This is not used directly by `NubladoBusiness`. It should be called by
        subclasses in `execute_code` in between each block of code that is
        executed.
        """
        with self.timings.start("execution_idle"):
            return await self.pause(self.options.execution_idle_time)

    async def shutdown(self) -> None:
        await self.hub_login()
        await self.delete_lab()

    async def idle(self) -> None:
        if self.options.jitter:
            self.logger.info("Idling...")
            with self.timings.start("idle"):
                extra_delay = self._random.uniform(0, self.options.jitter)
                await self.pause(self.options.idle_time + extra_delay)
        else:
            await super().idle()

    async def hub_login(self) -> None:
        self.logger.info("Logging in to hub")
        with self.timings.start("hub_login", self.annotations()) as sw:
            try:
                await self._client.auth_to_hub()
            except ne.JupyterProtocolError as exc:
                raise JupyterProtocolError.from_client_exception(
                    exc,
                    event=sw.event,
                    annotations=sw.annotations,
                    started_at=sw.start_time,
                ) from exc
            except ne.JupyterWebError as exc:
                raise JupyterWebError.from_client_exception(
                    exc,
                    event=sw.event,
                    annotations=sw.annotations,
                    started_at=sw.start_time,
                ) from exc

    async def spawn_lab(self) -> bool:
        with self.timings.start("spawn_lab", self.annotations()) as sw:
            try:
                result = await self._spawn_lab(sw)
            except:
                await self.events.nublado_spawn_lab.publish(
                    NubladoSpawnLab(
                        success=False,
                        duration=sw.elapsed,
                        **self.common_event_attrs(),
                    )
                )
                raise
        await self.events.nublado_spawn_lab.publish(
            NubladoSpawnLab(
                success=True, duration=sw.elapsed, **self.common_event_attrs()
            )
        )
        return result

    async def _spawn_lab(self, sw: Stopwatch) -> bool:  # noqa: C901
        # Ruff says this method is too complex, and it is, but it will become
        # less complex when we refactor and potentially Sentry-fy the slack
        # error reporting
        timeout = self.options.spawn_timeout
        try:
            await self._client.spawn_lab(self.options.image)
        except ne.JupyterWebError as exc:
            raise JupyterWebError.from_client_exception(
                exc,
                event=sw.event,
                annotations=sw.annotations,
                started_at=sw.start_time,
            ) from exc

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
            raise JupyterSpawnError(
                log,
                self.user.username,
                event=sw.event,
                started_at=sw.start_time,
            ) from None
        except ne.JupyterWebError as exc:
            raise JupyterWebError.from_client_exception(
                exc,
                event=sw.event,
                annotations=sw.annotations,
                started_at=sw.start_time,
            ) from exc
        except SlackException:
            raise
        except Exception as e:
            log = "\n".join([str(m) for m in log_messages])
            user = self.user.username
            raise JupyterSpawnError.from_exception(
                log,
                e,
                user,
                event=sw.event,
                annotations=sw.annotations,
                started_at=sw.start_time,
            ) from e

        # We only fall through if the spawn failed, timed out, or if we're
        # stopping the business.
        if self.stopping:
            return False
        log = "\n".join([str(m) for m in log_messages])
        if sw.elapsed > timeout:
            elapsed_seconds = round(sw.elapsed.total_seconds())
            msg = f"Lab did not spawn after {elapsed_seconds}s"
            raise JupyterTimeoutError(
                msg,
                self.user.username,
                log,
                event=sw.event,
                started_at=sw.start_time,
            )
        raise JupyterSpawnError(
            log,
            self.user.username,
            event=sw.event,
            started_at=sw.start_time,
        )

    async def lab_login(self) -> None:
        self.logger.info("Logging in to lab")
        with self.timings.start("lab_login", self.annotations()) as sw:
            try:
                await self._client.auth_to_lab()
            except ne.JupyterProtocolError as exc:
                raise JupyterProtocolError.from_client_exception(
                    exc,
                    event=sw.event,
                    annotations=sw.annotations,
                    started_at=sw.start_time,
                ) from exc

    @asynccontextmanager
    async def open_session(
        self, notebook: str | None = None
    ) -> AsyncIterator[JupyterLabSession]:
        self.logger.info("Creating lab session")
        opts = {"max_websocket_size": self.options.max_websocket_message_size}
        stopwatch = self.timings.start("create_session", self.annotations())
        async with self._client.open_lab_session(notebook, **opts) as session:
            stopwatch.stop()
            with self.timings.start("execute_setup", self.annotations()):
                await self.setup_session(session)
            yield session
            await self.lab_login()
            self.logger.info("Deleting lab session")
            stopwatch = self.timings.start(
                "delete_session", self.annotations()
            )
        stopwatch.stop()
        self._node = None

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
        if self.options.get_node:
            self._node = await session.run_python(_GET_NODE)
            self.logger.info(f"Running on node {self._node}")
        if self.options.working_directory:
            path = self.options.working_directory
            code = _CHDIR_TEMPLATE.format(wd=path)
            self.logger.info(f"Changing directories to {path}")
            await session.run_python(code)

    async def delete_lab(self) -> None:
        with self.timings.start("delete_lab", self.annotations()) as sw:
            try:
                result = await self._delete_lab(sw)
            except:
                await self.events.nublado_delete_lab.publish(
                    NubladoDeleteLab(
                        success=False,
                        duration=sw.elapsed,
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
                    duration=sw.elapsed,
                    **self.common_event_attrs(),
                )
            )

    async def _delete_lab(self, sw: Stopwatch) -> bool:
        """Delete a lab.

        Parameters
        ----------
        sw
            A Stopwatch to time the lab deletion

        Returns
        -------
        bool
            True if we know the lab was successfully deleted, False if we
            didn't wait to find out if the lab was successfully deleted.
        """
        self.logger.info("Deleting lab")
        try:
            await self._client.stop_lab()
        except ne.JupyterWebError as exc:
            raise JupyterWebError.from_client_exception(
                exc,
                event=sw.event,
                annotations=sw.annotations,
                started_at=sw.start_time,
            ) from exc
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
                    jte = JupyterTimeoutError(
                        msg,
                        self.user.username,
                        started_at=start,
                        event=sw.event,
                    )
                    jte.annotations["image"] = self.options.image.description
                    raise jte
            msg = f"Waiting for lab deletion ({elapsed_seconds}s elapsed)"
            self.logger.info(msg)
            if not await self.pause(timedelta(seconds=2)):
                return False

        self.logger.info("Lab successfully deleted")
        self._image = None
        return True

    def dump(self) -> NubladoBusinessData:
        return NubladoBusinessData(
            image=self._image, **super().dump().model_dump()
        )
