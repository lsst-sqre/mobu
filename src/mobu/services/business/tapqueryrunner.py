"""Run queries against a TAP service."""

from __future__ import annotations

from random import SystemRandom

from httpx import AsyncClient
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
    http_client
        Shared HTTP client for general web access.
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
        http_client: AsyncClient,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            http_client=http_client,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._random = SystemRandom()

    def get_next_query(self) -> str:
        return self._random.choice(self.options.queries)
