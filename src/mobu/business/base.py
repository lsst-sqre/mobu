"""Base class for business logic for mobu."""

from __future__ import annotations

import asyncio
from asyncio import Queue, QueueEmpty, TimeoutError
from enum import Enum
from typing import TYPE_CHECKING

from ..models.business import BusinessData
from ..timings import Timings

if TYPE_CHECKING:
    from structlog import BoundLogger

    from ..models.business import BusinessConfig
    from ..models.user import AuthenticatedUser

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
    which generally does not need to be overridden.

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

    async def run(self) -> None:
        """The core business logic, run in a background task."""
        self.logger.info("Starting up...")
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

        # Tell the control channel we've processed the stop command.
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

    async def shutdown(self) -> None:
        """Any cleanup to do before exiting after stopping."""
        pass

    async def stop(self) -> None:
        """Tell the running background task to stop and wait for that."""
        await self.control.put(BusinessCommand.STOP)
        await self.control.join()
        self.logger.info("Stopped")

    async def pause(self, seconds: float) -> None:
        """Pause for up to the number of seconds, handling commands."""
        if self.stopping:
            return
        try:
            if seconds:
                command = await asyncio.wait_for(self.control.get(), seconds)
            else:
                command = self.control.get_nowait()
        except (TimeoutError, QueueEmpty):
            return
        else:
            if command == BusinessCommand.STOP:
                self.stopping = True

    def dump(self) -> BusinessData:
        return BusinessData(
            name=type(self).__name__,
            config=self.config,
            failure_count=self.failure_count,
            success_count=self.success_count,
            timings=self.timings.dump(),
        )
