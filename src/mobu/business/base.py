"""Base class for business logic for mobu."""

from __future__ import annotations

import asyncio
from asyncio import Queue, QueueEmpty, TimeoutError
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterable, AsyncIterator, TypeVar

from structlog import BoundLogger

from ..models.business import BusinessConfig, BusinessData
from ..models.user import AuthenticatedUser
from ..timings import Timings
from ..util import wait_first

T = TypeVar("T")

__all__ = ["Business"]


class BusinessCommand(Enum):
    """Commands sent over the internal control queue."""

    STOP = "STOP"


class Business:
    """Base class for monkey business (one type of repeated operation).

    The basic flow for a monkey business is as follows:

    - Run ``startup``
    - In a loop, run ``execute`` followed by ``idle`` until told to stop
    - When told to stop, run ``shutdown``

    Subclasses should override ``startup``, ``execute``, and ``shutdown`` to
    add appropriate behavior.  ``idle`` by default waits for ``idle_time``,
    which generally does not need to be overridden.  Subclasses should also
    override ``close`` to shut down any object state created in ``__init__``.

    All delays should be done by calling ``pause``, and the caller should
    check ``self.stopping`` and exit any loops if it is `True` after calling
    ``pause``.

    Parameters
    ----------
    logger : `structlog.BoundLogger`
        Logger to use to report the results of business.
    options : Dict[`str`, Any]
        Configuration options for the business.
    token : `str`
        The authentication token to use for internal calls.
    """

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        self.logger = logger
        self.config = business_config
        self.user = user
        self.success_count = 0
        self.failure_count = 0
        self.timings = Timings()
        self.control: Queue[BusinessCommand] = Queue()
        self.stopping = False

    async def close(self) -> None:
        """Clean up any business state on shutdown."""
        pass

    async def run(self) -> None:
        """The core business logic, run in a background task."""
        self.logger.info("Starting up...")
        try:
            await self.startup()

            while not self.stopping:
                self.logger.info("Starting next iteration")
                try:
                    await self.execute()
                    self.success_count += 1
                except Exception:
                    self.failure_count += 1
                    raise
                await self.idle()

            self.logger.info("Shutting down...")
            await self.shutdown()
            await self.close()
        finally:
            # Tell the control channel we've processed the stop command.
            if self.stopping:
                self.control.task_done()

    async def startup(self) -> None:
        """Run before the start of the first iteration and then not again."""
        pass

    async def execute(self) -> None:
        """The business done in each loop."""
        pass

    async def idle(self) -> None:
        """The idle pause at the end of each loop."""
        self.logger.info("Idling...")
        with self.timings.start("idle"):
            await self.pause(self.config.idle_time)

    async def error_idle(self) -> None:
        """The idle pause after an error.

        This happens outside of ``run`` and therefore must handle
        acknowledging a shutdown request.
        """
        self.logger.warning("Restarting failed monkey after 60s")
        try:
            await self.pause(60)
        finally:
            if self.stopping:
                self.control.task_done()

    async def shutdown(self) -> None:
        """Any cleanup to do before exiting after stopping."""
        pass

    async def stop(self) -> None:
        """Tell the running background task to stop and wait for that."""
        self.stopping = True
        await self.control.put(BusinessCommand.STOP)
        await self.control.join()
        self.logger.info("Stopped")
        await self.close()

    async def pause(self, seconds: float) -> None:
        """Pause for up to the number of seconds, handling commands."""
        if self.stopping:
            return
        try:
            if seconds:
                await asyncio.wait_for(self.control.get(), seconds)
            else:
                self.control.get_nowait()
        except (TimeoutError, QueueEmpty):
            return

    async def iter_with_timeout(
        self, iterable: AsyncIterable[T], timeout: float
    ) -> AsyncIterator[T]:
        """Run an iterator with a timeout.

        Returns the next element of the iterator on success and ends the
        iterator on timeout or if the business was told to shut down.  (The
        latter two can be distinguished by checking ``self.stopping``.)

        Notes
        -----
        This is unfortunately somewhat complex because we want to read from an
        iterator of messages (progress for spawn or WebSocket messages for
        code execution) while simultaneously checking our control queue for a
        shutdown message and imposing a timeout.

        Do this by creating two awaitables, one pause that handles the control
        queue and the timeout and the other that waits on the progress
        iterator, and then use the ``wait_first`` utility function to wait for
        the first one that finishes and abort the other one.
        """
        iterator = iterable.__aiter__()

        # While it works for our current code to pass the results of __anext__
        # directly into wait_first and thus into asyncio.create_task, mypy
        # complains because technically the return value of __anext__ can be
        # any Awaitable and does not need to be a Coroutine (which is required
        # for asyncio.create_task).  Turn it into an explicit Coroutine to
        # guarantee this will always work correctly.
        async def iter_next() -> T:
            return await iterator.__anext__()

        start = datetime.now(tz=timezone.utc)
        while True:
            now = datetime.now(tz=timezone.utc)
            remaining = timeout - (now - start).total_seconds()
            if remaining < 0:
                break
            result = await wait_first(iter_next(), self.pause(timeout))
            if result is None or self.stopping:
                break
            yield result

    def dump(self) -> BusinessData:
        return BusinessData(
            name=type(self).__name__,
            failure_count=self.failure_count,
            success_count=self.success_count,
            timings=self.timings.dump(),
        )
