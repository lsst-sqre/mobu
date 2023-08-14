"""Holds timing information for mobu events."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import TracebackType
from typing import Literal, Self

from safir.datetime import current_datetime

from ..exceptions import MobuSlackException
from ..models.timings import StopwatchData


class Timings:
    """Holds a collection of timings.

    The underlying data structure is a list of `Stopwatch` objects with some
    machinery to start and stop timers.
    """

    def __init__(self) -> None:
        self._last: Stopwatch | None = None
        self._stopwatches: list[Stopwatch] = []

    def start(
        self, event: str, annotations: dict[str, str] | None = None
    ) -> Stopwatch:
        """Start a stopwatch.

        Examples
        --------
        This should normally be used as a context manager:

        .. code-block:: python

           with timings.start("event", annotation):
               ...
        """
        if not annotations:
            annotations = {}
        stopwatch = Stopwatch(event, annotations, self._last)
        self._stopwatches.append(stopwatch)
        self._last = stopwatch
        return stopwatch

    def dump(self) -> list[StopwatchData]:
        """Convert the stored timings to a dictionary."""
        return [s.dump() for s in self._stopwatches]


class Stopwatch:
    """Container for time data.

    A metric container for time data and its serialization. Normally, this
    should be used as a context manager and it will automatically close the
    timer when the context manager is exited. It can instead be stored in a
    variable and stopped explicitly with ``stop`` in cases where a context
    manager isn't appropriate.

    Parameters
    ----------
    event
        The name of the event.
    annotation
        Arbitrary annotations.
    previous
        The previous stopwatch, used to calculate the idle time between
        timed events.
    """

    def __init__(
        self,
        event: str,
        annotations: dict[str, str],
        previous: Stopwatch | None = None,
    ) -> None:
        self.event = event
        self.annotations = annotations
        self.start_time = current_datetime(microseconds=True)
        self.stop_time: datetime | None = None
        self.failed = False
        self._previous = previous

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self.stop_time = current_datetime(microseconds=True)
        if exc_val:
            self.failed = True
        if exc_val and isinstance(exc_val, MobuSlackException):
            exc_val.started_at = self.start_time
            exc_val.event = self.event
            exc_val.annotations = self.annotations
        return False

    @property
    def elapsed(self) -> timedelta:
        """Return the total time (to the present if not stopped)."""
        if self.stop_time:
            return self.stop_time - self.start_time
        else:
            return current_datetime(microseconds=True) - self.start_time

    def dump(self) -> StopwatchData:
        """Convert to a Pydantic model."""
        elapsed = None
        if self.stop_time:
            elapsed = (self.stop_time - self.start_time).total_seconds()
        return StopwatchData(
            event=self.event,
            annotations=self.annotations,
            start=self.start_time,
            stop=self.stop_time,
            elapsed=elapsed,
            failed=self.failed,
        )

    def stop(self) -> None:
        """Explicitly stop the stopwatch, outside of a context manager."""
        self.stop_time = current_datetime(microseconds=True)
