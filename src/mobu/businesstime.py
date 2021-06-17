"""https://youtu.be/WGOohBytKTU
"""

from dataclasses import dataclass, field

from mobu.business import Business
from mobu.timing import TimingData


@dataclass
class BusinessTime(Business):
    timings: list[TimingData] = field(default_factory=list)

    def dump(self):
        return {
            "name": "BusinessTime",
            "timings": [x.dump() for x in self.timings],
        }
