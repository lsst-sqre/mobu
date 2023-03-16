"""Utility functions for mobu."""

from __future__ import annotations

import asyncio
from asyncio import Task
from collections.abc import Awaitable, Callable, Coroutine
from typing import TypeVar

T = TypeVar("T")

__all__ = ["schedule_periodic", "wait_first"]


def schedule_periodic(
    func: Callable[[], Awaitable[None]], interval_seconds: int
) -> Task:
    """Schedule a function to run periodically."""

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await func()

    return asyncio.ensure_future(loop())


async def wait_first(*args: Coroutine[None, None, T]) -> T | None:
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
    gather = asyncio.gather(*pending)
    gather.cancel()
    try:
        await gather
    except asyncio.CancelledError:
        pass
    try:
        return done.pop().result()
    except StopAsyncIteration:
        return None
