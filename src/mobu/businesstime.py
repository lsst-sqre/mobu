"""https://youtu.be/WGOohBytKTU
"""

from dataclasses import dataclass, field
from typing import List, Optional

from mobu.business import Business
from mobu.timing import Stopwatch


@dataclass
class BusinessTime(Business):
    timings: List[Stopwatch] = field(default_factory=list)

    def start_event(
        self,
        event: str,
        annotation: dict = {},
        previous: Optional[Stopwatch] = None,
    ) -> None:
        # We can intentionally overload previous with a prior event if we
        #  want, in order to nest events.
        if not previous:
            if self.timings:
                previous = self.timings[-1]
        watch = Stopwatch.start(
            event, annotation=annotation, previous=previous
        )
        self.timings.append(watch)

    def stop_current_event(self) -> None:
        if self.timings:
            self.timings[-1].stop()

    def get_current_event(self) -> Optional[Stopwatch]:
        if not self.timings:
            return None
        return self.timings[-1]

    def dump(self) -> dict:
        return {
            "name": "BusinessTime",
            "timings": [x.dump() for x in self.timings],
        }
