"""Base class for business logic for mobu."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..models.business import BusinessData
from ..timings import Timings

if TYPE_CHECKING:
    from structlog import BoundLogger

    from ..models.business import BusinessConfig
    from ..models.user import AuthenticatedUser

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
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        self.logger = logger
        self.config = business_config
        self.user = user
        self.success_count = 0
        self.failure_count = 0
        self.timings = Timings()

    async def run(self) -> None:
        while True:
            self.logger.info("Idling...")
            with self.timings.start("idle"):
                await asyncio.sleep(5)
            self.success_count += 1

    async def stop(self) -> None:
        pass

    def dump(self) -> BusinessData:
        return BusinessData(
            name=type(self).__name__,
            config=self.config,
            failure_count=self.failure_count,
            success_count=self.success_count,
            timings=self.timings.dump(),
        )
