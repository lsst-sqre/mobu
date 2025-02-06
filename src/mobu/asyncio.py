"""asyncio utility functions for mobu."""

from __future__ import annotations

import asyncio
import contextlib
from asyncio import Task
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from datetime import timedelta
from types import TracebackType
from typing import Literal, TypeVar

T = TypeVar("T")

__all__ = [
    "aclosing_iter",
    "schedule_periodic",
    "wait_first",
]


class aclosing_iter[T: AsyncIterator](AbstractAsyncContextManager):  # noqa: N801
    """Automatically close async iterators that are generators.

    Python supports two ways of writing an async iterator: a true async
    iterator, and an async generator. Generators support additional async
    context, such as yielding from inside an async context manager, and
    therefore require cleanup by calling their `aclose` method once the
    generator is no longer needed. This step is done automatically by the
    async loop implementation when the generator is garbage-collected, but
    this may happen at an arbitrary point and produces pytest warnings
    saying that the `aclose` method on the generator was never called.

    This class provides a variant of `contextlib.aclosing` that can be
    used to close generators masquerading as iterators. Many Python libraries
    implement `__aiter__` by returning a generator rather than an iterator,
    which is equivalent except for this cleanup behavior. Async iterators do
    not require this explicit cleanup step because they don't support async
    context managers inside the iteration. Since the library is free to change
    from a generator to an iterator at any time, and async iterators don't
    require this cleanup and don't have `aclose` methods, the `aclose` method
    should be called only if it exists.
    """

    def __init__(self, thing: T) -> None:
        self.thing = thing

    async def __aenter__(self) -> T:
        return self.thing

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        # Only call aclose if the method is defined, which we take to mean that
        # this iterator is actually a generator.
        if getattr(self.thing, "aclose", None):
            await self.thing.aclose()  # type: ignore[attr-defined]
        return False


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
    with contextlib.suppress(asyncio.CancelledError):
        gather = asyncio.gather(*pending)
        gather.cancel()
        await gather
    try:
        return done.pop().result()
    except StopAsyncIteration:
        return None
