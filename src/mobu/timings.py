"""Holds timing information for mobu events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

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
        self, event: str, annotation: Optional[Dict[str, Any]] = None
    ) -> Stopwatch:
        """Start a stopwatch.

        Examples
        --------
        This should normally be used as a context manager:

        .. code-block:: python

           with timings.start("event", annotation):
               ...
        """
        if not annotation:
            annotation = {}
        stopwatch = Stopwatch(event, annotation, self._last)
        self._stopwatches.append(stopwatch)
        self._last = stopwatch
        return stopwatch

    def dump(self) -> List[Dict[str, Any]]:
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
        annotation: Dict[str, Any],
        previous: Optional[Stopwatch] = None,
    ) -> None:
        self.event = event
        self.annotation = annotation
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
        return False

    @property
    def elapsed(self) -> timedelta:
        """Return the total time (to the present if not stopped)."""
        if self.stop_time:
            return self.stop_time - self.start_time
        else:
            return datetime.now(tz=timezone.utc) - self.start_time

    def dump(self) -> Dict[str, Any]:
        """Convert to a dictionary.

        You can't directly JSON-dump datetimes/timedeltas.  So instead
        we convert the time to its ISO 8601 format.  This can be converted
        back to a timestamp with datetime.fromisoformat().

        Likewise, the elapsed time is a float representing number of
        seconds, which you can just pass to a timedelta constructor.
        """
        elapsed = None
        if self.stop_time:
            elapsed = (self.stop_time - self.start_time).total_seconds()
        data = {
            "event": self.event,
            "annotation": self.annotation,
            "start": self.start_time.isoformat(),
            "stop": self.stop_time.isoformat() if self.stop_time else None,
            "elapsed": elapsed,
        }
        if self._previous:
            data["previous"] = {
                "event": self._previous.event,
                "start": self._previous.start_time.isoformat(),
            }
        if self._previous and self._previous.stop_time:
            idle = (self.start_time - self._previous.stop_time).total_seconds()
            data["elapsed_since_previous_stop"] = idle
        return data
