"""Holds timing information for mobu events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .exceptions import SlackError
from .models.timings import StopwatchData

if TYPE_CHECKING:
    from datetime import timedelta
    from types import TracebackType
    from typing import Any, Dict, List, Literal, Optional


class Timings:
    """Holds a collection of timings.

    The underlying data structure is a list of `Stopwatch` objects with some
    machinery to start and stop timers.
    """

    def __init__(self) -> None:
        self._last: Optional[Stopwatch] = None
        self._stopwatches: List[Stopwatch] = []

    def start(
        self, event: str, annotations: Optional[Dict[str, Any]] = None
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

    def dump(self) -> List[StopwatchData]:
        """Convert the stored timings to a dictionary."""
        return [s.dump() for s in self._stopwatches]


class Stopwatch:
    """Container for time data.

    A metric container for time data and its serialization.  Use as a context
    manager.  Will automatically close the timer when the context manager is
    exited.

    Parameters
    ----------
    event : `str`
        The name of the event.
    annotation : Dict[`str`, Any], optional
        Arbitrary annotations.
    previous : `Stopwatch`, optional
        The previous stopwatch, used to calculate the idle time between
        timed events.
    """

    def __init__(
        self,
        event: str,
        annotations: Dict[str, Any],
        previous: Optional[Stopwatch] = None,
    ) -> None:
        self.event = event
        self.annotations = annotations
        self.start_time = datetime.now(tz=timezone.utc)
        self.stop_time: Optional[datetime] = None
        self._previous = previous

    def __enter__(self) -> Stopwatch:
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[TracebackType],
    ) -> Literal[False]:
        self.stop_time = datetime.now(tz=timezone.utc)
        if exc_val and isinstance(exc_val, SlackError):
            exc_val.started = self.start_time
            exc_val.event = self.event
            exc_val.annotations = self.annotations
        return False

    @property
    def elapsed(self) -> timedelta:
        """Return the total time (to the present if not stopped)."""
        if self.stop_time:
            return self.stop_time - self.start_time
        else:
            return datetime.now(tz=timezone.utc) - self.start_time

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
        )
