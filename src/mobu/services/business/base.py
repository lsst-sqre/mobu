"""Base class for business logic for mobu."""

from __future__ import annotations

import asyncio
from abc import ABCMeta, abstractmethod
from asyncio import Queue, QueueEmpty
from collections.abc import AsyncIterable, AsyncIterator
from datetime import timedelta
from enum import Enum
from typing import Generic, TypeVar

from httpx import AsyncClient
from safir.datetime import current_datetime
from structlog.stdlib import BoundLogger

from ...asyncio import wait_first
from ...models.business.base import BusinessData, BusinessOptions
from ...models.user import AuthenticatedUser
from ..timings import Timings

T = TypeVar("T", bound="BusinessOptions")
U = TypeVar("U")

__all__ = ["Business"]


class BusinessCommand(Enum):
    """Commands sent over the internal control queue."""

    STOP = "STOP"


class Business(Generic[T], metaclass=ABCMeta):
    """Base class for monkey business (one type of repeated operation).

    The basic flow for a monkey business is as follows:

    - Run ``startup``
    - In a loop, run ``execute`` followed by ``idle`` until told to stop
    - When told to stop, run ``shutdown``

    Subclasses should override ``startup``, ``execute``, and ``shutdown`` to
    add appropriate behavior.  ``idle`` by default waits for ``idle_time``,
    which generally does not need to be overridden.  Subclasses should also
    override ``close`` to free any resources allocated in ``__init__``.

    All delays should be done by calling ``pause``, and the caller should
    check ``self.stopping`` and exit any loops if it is `True` after calling
    ``pause``.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    http_client
        Shared HTTP client.
    logger
        Logger to use to report the results of business.

    Attributes
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    http_client
        Shared HTTP client.
    logger
        Logger to use to report the results of business. This will generally
        be attached to a file rather than the main logger.
    success_count
        Number of successes.
    failure_count
        Number of failures.
    timings
        Execution timings.
    stopping
        Whether `stop` has been called and further execution should stop.
    """

    def __init__(
        self,
        options: T,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        self.options = options
        self.user = user
        self.http_client = http_client
        self.logger = logger
        self.success_count = 0
        self.failure_count = 0
        self.timings = Timings()
        self.control: Queue[BusinessCommand] = Queue()
        self.stopping = False
        self.refreshing = False

    # Methods that should be overridden by child classes if needed.

    async def startup(self) -> None:
        """Run before the start of the first iteration and then not again."""

    @abstractmethod
    async def execute(self) -> None:
        """Execute the core of each business loop."""

    async def close(self) -> None:
        """Clean up any allocated resources.

        This should be overridden by child classes to free any resources that
        were allocated in ``__init__``.
        """

    async def shutdown(self) -> None:
        """Perform any cleanup required after stopping."""

    # Public Business API called by the Monkey class. These methods handle the
    # complex state logic of looping and handling a stop signal and should not
    # be overridden.

    async def run(self) -> None:
        """Execute the core business logic.

        Calls `startup`, and then loops calling `execute` followed by `idle`,
        tracking failures by watching for exceptions and updating
        ``success_count`` and ``failure_count``. When told to stop, calls
        `shutdown` followed by `close`.

        This method is normally run in a background task.
        """
        self.logger.info("Starting up...")
        try:
            try:
                await self.startup()
            except Exception:
                # Strictly speaking, this is not an iteration, but unless we
                # count startup failure as a failed iteration, a business that
                # keeps failing during startup reports 100% success in the
                # flock summary.
                self.failure_count += 1
                raise

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

    async def run_once(self) -> None:
        """Execute the core business logic, only once.

        Calls `startup`, `execute`, `shutdown`, and `close`.
        """
        self.logger.info("Starting up...")
        try:
            await self.startup()
            await self.execute()
            self.logger.info("Shutting down...")
            await self.shutdown()
        finally:
            await self.close()

    async def idle(self) -> None:
        """Pause at the end of each business loop."""
        self.logger.info("Idling...")
        with self.timings.start("idle"):
            await self.pause(self.options.idle_time)

    async def error_idle(self) -> None:
        """Pause after an error and before attempting to restart.

        Thia is called directly by `~mobu.services.monkey.Monkey` rather than
        by the business. It happens outside of `run` and therefore must handle
        acknowledging a shutdown request.
        """
        error_idle = self.options.error_idle_time
        self.logger.warning(f"Restarting failed monkey after {error_idle}s")
        try:
            await self.pause(error_idle)
        finally:
            if self.stopping:
                self.control.task_done()

    async def stop(self) -> None:
        """Tell the running background task to stop and wait for that."""
        self.stopping = True
        self.logger.info("Stopping...")
        await self.control.put(BusinessCommand.STOP)
        await self.control.join()
        self.logger.info("Stopped")

    def signal_refresh(self) -> None:
        self.refreshing = True

    # Utility functions that can be used by child classes.

    async def pause(self, interval: timedelta) -> bool:
        """Pause for up to the given interval, handling commands.

        Parameters
        ----------
        seconds
            How long to wait.

        Returns
        -------
        bool
            `False` if the business has been told to stop, `True` otherwise.
        """
        if self.stopping:
            return False
        try:
            if interval:
                seconds = interval.total_seconds()
                await asyncio.wait_for(self.control.get(), seconds)
                return False
            else:
                self.control.get_nowait()
                return False
        except (TimeoutError, QueueEmpty):
            return True

    async def iter_with_timeout(
        self, iterable: AsyncIterable[U], timeout: timedelta
    ) -> AsyncIterator[U]:
        """Run an iterator with a timeout.

        Returns the next element of the iterator on success and ends the
        iterator on timeout or if the business was told to shut down.  (The
        latter two can be distinguished by checking ``self.stopping``.)

        Parameters
        ----------
        iterable
            Any object that supports the async iterable protocol.
        timeout
            How long to wait for each new iterator result.

        Yields
        ------
        typing.Any
            The next result of the iterable passed as ``iterable``.

        Raises
        ------
        StopIteration
            Raised when the iterable is exhausted, a timeout occurs, or the
            business was signaled to stop by calling `stop`.

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
        async def iter_next() -> U:
            return await iterator.__anext__()

        start = current_datetime(microseconds=True)
        while True:
            now = current_datetime(microseconds=True)
            remaining = timeout - (now - start)
            if remaining < timedelta(seconds=0):
                break
            pause = self._pause_no_return(timeout)
            result = await wait_first(iter_next(), pause)
            if result is None or self.stopping:
                break
            yield result

    def dump(self) -> BusinessData:
        return BusinessData(
            name=type(self).__name__,
            failure_count=self.failure_count,
            success_count=self.success_count,
            refreshing=self.refreshing,
            timings=self.timings.dump(),
        )

    async def _pause_no_return(self, interval: timedelta) -> None:
        """Pause for up to an interval, handling commands.

        The same as `pause`, but returns `None`, needed for proper typing of
        `iter_with_timeout`.

        Parameters
        ----------
        interval
            How long to wait.
        """
        if self.stopping:
            return
        try:
            if interval:
                seconds = interval.total_seconds()
                await asyncio.wait_for(self.control.get(), seconds)
            else:
                self.control.get_nowait()
        except (TimeoutError, QueueEmpty):
            pass
