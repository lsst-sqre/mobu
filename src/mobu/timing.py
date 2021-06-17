from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TimeInfo:
    """A metric container for time data and its serialization.  Contains
    both an absolute timestamp and a time-elapsed-since-previous-timeinfo
    field."""

    absolute: datetime
    elapsed: timedelta

    @classmethod
    def stamp(cls, previous: Optional["TimeInfo"] = None) -> "TimeInfo":
        now = datetime.now(timezone.utc)
        if not previous:
            elapsed = timedelta(0)
        else:
            elapsed = now - previous.absolute
        return cls(absolute=now, elapsed=elapsed)

    def dump(self) -> Dict[str, Any]:
        """You can't directly JSON-dump datetimes/timedeltas.  So instead
        we convert the time to its ISO 8601 format.  This can be converted
        back to a timestamp with datetime.fromisoformat().

        Likewise, the elapsed time is a float representing number of
        seconds, which you can just pass to a timedelta constructor.
        """
        return {
            "absolute": self.absolute.isoformat(),
            "elapsed": self.elapsed.total_seconds(),
        }


@dataclass
class TimingData:
    """Base timing class.  Only has start and stop times."""

    start: Optional[TimeInfo] = None
    stop: Optional[TimeInfo] = None
    name: str = "Timing"

    def dump(self):
        """This should work for sane subclasses too.  The magic is in
        _itemdump() (well, and dataclasses.fields())"""
        r = {}
        for t in fields(self):
            r[t.name] = self._itemdump(t.name)
        return r

    def _itemdump(self, name: str) -> str:
        """This is a special-purpose serializer, effectively.  An _itemdump()
        of None or a string is itself, a list calls the dump() method of all
        its items, and anything else is presumed to have a dump() method
        of its own to call.
        """
        item = getattr(self, name, None)
        if item is None or (type(item) is str):
            return item
        elif type(item) is list:
            return [x.dump() for x in item]
        return item.dump()


@dataclass
class CodeTimingData(TimingData):
    """Annotates the timing with the code being timed."""

    name: str = "CodeTiming"
    code: str = ""


@dataclass
class QueryTimingData(TimingData):
    """Annotates the timing with the query being timed."""

    name: str = "QueryTiming"
    query: str = ""


@dataclass
class HubLoginTimingData(TimingData):
    """Used for timing Hub login time."""

    login_complete: Optional[TimeInfo] = None
    name: str = "HubLoginTiming"


@dataclass
class LabLoopTimingData(HubLoginTimingData):
    """Used for timing Lab container creation/deletion."""

    lab_created: Optional[TimeInfo] = None
    lab_complete: Optional[TimeInfo] = None
    lab_deleted: Optional[TimeInfo] = None
    name: str = "LabLoopTiming"


@dataclass
class PythonTimingData(LabLoopTimingData):
    """Used for timing Python kernel creation and execution."""

    kernel_created: Optional[TimeInfo] = None
    name: str = "PythonTiming"
    code: list[CodeTimingData] = field(default_factory=list)


@dataclass
class NotebookTimingData(PythonTimingData):
    name: str = "NotebookTiming"
    repo_cloned: Optional[TimeInfo] = None


@dataclass
class TAPQueryTimingData(TimingData):
    name: str = "TAPQueryTiming"
    query: list[QueryTimingData] = field(default_factory=list)
