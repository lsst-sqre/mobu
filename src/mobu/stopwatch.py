"""Holds timing information for mobu events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import timedelta
    from typing import Any, Dict, Optional


class StopwatchAlreadyStopped(Exception):
    """The stopwatch was not running when it was stopped."""


class Stopwatch:
    """Container for time data.

    A metric container for time data and its serialization.  Create it with
    start(), stop it with stop().  It will fill out its elapsed field on
    stop().

    Give it an event (an arbitrary string) and an optional annotation (an
    arbitrary dict).
    """

    @classmethod
    def start(
        cls,
        event: str,
        annotation: Optional[Dict[str, Any]] = None,
        previous: Optional[Stopwatch] = None,
    ) -> Stopwatch:
        return cls(
            start_time=datetime.now(timezone.utc),
            event=event,
            annotation=annotation if annotation else {},
            previous=previous,
        )

    def __init__(
        self,
        start_time: datetime,
        event: str,
        annotation: Dict[str, Any],
        previous: Optional[Stopwatch] = None,
    ) -> None:
        self.event = event
        self.annotation = annotation
        self.start_time = start_time
        self.stop_time: Optional[datetime] = None
        self.elapsed: Optional[timedelta] = None
        self._previous = previous

    def stop(self) -> None:
        """Stop the timer.

        After this call, the timer cannot be used further except to recover
        its attribute information.
        """
        if self.stop_time:
            msg = f"Stopwatch already stopped at {self.stop_time.isoformat()}"
            raise StopwatchAlreadyStopped(msg)
        now = datetime.now(timezone.utc)
        self.stop_time = now
        self.elapsed = now - self.start_time

    def dump(self) -> Dict[str, Any]:
        """Convert to a dictionary.

        You can't directly JSON-dump datetimes/timedeltas.  So instead
        we convert the time to its ISO 8601 format.  This can be converted
        back to a timestamp with datetime.fromisoformat().

        Likewise, the elapsed time is a float representing number of
        seconds, which you can just pass to a timedelta constructor.
        """
        data = {
            "event": self.event,
            "annotation": self.annotation,
            "start": self.start_time.isoformat(),
            "stop": self.stop_time.isoformat() if self.stop_time else None,
            "elapsed": self.elapsed.total_seconds() if self.elapsed else None,
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
