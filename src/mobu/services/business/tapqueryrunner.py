"""Run queries against a TAP service."""

from __future__ import annotations

from random import SystemRandom

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

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
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: TAPQueryRunnerOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._random = SystemRandom()

    def get_next_query(self) -> str:
        return self._random.choice(self.options.queries)
