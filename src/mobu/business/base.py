"""Base class for business logic for mobu."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..timing import Stopwatch

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional

    from structlog import BoundLogger

    from ..user import User

__all__ = ["Business"]


class Business:
    """Base class for monkey business (one type of repeated operation).

    Parameters
    ----------
    logger : `structlog.BoundLogger`
        Logger to use to report the results of business.
    options : Dict[`str`, Any]
        Configuration options for the business.
    token : `str`
        The authentication token to use for internal calls.
    """

    def __init__(
        self, logger: BoundLogger, options: Dict[str, Any], user: User
    ) -> None:
        self.logger = logger
        self.options = options
        self.user = user
        self.timings: List[Stopwatch] = []

    async def run(self) -> None:
        while True:
            self.logger.info("Idling...")
            await asyncio.sleep(5)

    async def stop(self) -> None:
        pass

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

    def dump(self) -> Dict[str, Any]:
        return {
            "name": type(self).__name__,
            "timings": [x.dump() for x in self.timings],
        }
