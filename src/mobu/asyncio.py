"""asyncio utility functions for mobu."""

import asyncio
import contextlib
from asyncio import Task
from collections.abc import Awaitable, Callable, Coroutine
from datetime import timedelta

__all__ = [
    "schedule_periodic",
    "wait_first",
]


def schedule_periodic(
    func: Callable[[], Awaitable[None]], interval: timedelta
) -> Task:
    """Schedule a function to run periodically.

    Parmaeters
    ----------
    func
        Async function to call periodically.
    interval
        How long to pause between executions.

    Returns
    -------
    Task
        Running task that will call the function periodically.
    """

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval.total_seconds())
            await func()

    return asyncio.ensure_future(loop())


async def wait_first[T](*args: Coroutine[None, None, T]) -> T | None:
    """Return the result of the first awaitable to finish.

    The other awaitables will be cancelled.  The first awaitable determines
    the expected return type, and all other awaitables must return either the
    same return type or `None`.

    Notes
    -----
    Taken from https://stackoverflow.com/questions/31900244/
    """
    done, pending = await asyncio.wait(
        [asyncio.create_task(a) for a in args],
        return_when=asyncio.FIRST_COMPLETED,
    )
    with contextlib.suppress(asyncio.CancelledError):
        gather = asyncio.gather(*pending)
        gather.cancel()
        await gather
    try:
        return done.pop().result()
    except StopAsyncIteration:
        return None
