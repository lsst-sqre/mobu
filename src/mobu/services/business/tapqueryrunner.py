"""Run queries against a TAP service."""

from __future__ import annotations

from random import SystemRandom
from typing import override

from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.tapqueryrunner import TAPQueryRunnerOptions
from ...models.user import AuthenticatedUser
from .tap import TAPBusiness

__all__ = ["TAPQueryRunner"]


class TAPQueryRunner(TAPBusiness):
    """Run queries against TAP.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    events
        Event publishers.
    logger
        Logger to use to report the results of business.
    flock
        Flock that is running this business, if it is running in a flock.
    """

    def __init__(
        self,
        *,
        options: TAPQueryRunnerOptions,
        user: AuthenticatedUser,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._random = SystemRandom()

    @override
    def get_next_query(self) -> str:
        return self._random.choice(self.options.queries)
