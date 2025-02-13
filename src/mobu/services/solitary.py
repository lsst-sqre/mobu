"""Manager for a solitary monkey."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ..events import Events
from ..models.solitary import SolitaryConfig, SolitaryResult
from ..services.repo import RepoManager
from ..storage.gafaelfawr import GafaelfawrStorage
from .monkey import Monkey

__all__ = ["Solitary"]


class Solitary:
    """Runs a single monkey to completion and reports its results.

    Parameters
    ----------
    solitary_config
        Configuration for the monkey.
    gafaelfawr_storage
        Gafaelfawr storage client.
    http_client
        Shared HTTP client.
    events
        Event publishers.
    repo_manager
        For efficiently cloning git repos.
    logger
        Global logger.
    """

    def __init__(
        self,
        *,
        solitary_config: SolitaryConfig,
        gafaelfawr_storage: GafaelfawrStorage,
        http_client: AsyncClient,
        events: Events,
        repo_manager: RepoManager,
        logger: BoundLogger,
    ) -> None:
        self._config = solitary_config
        self._gafaelfawr = gafaelfawr_storage
        self._http_client = http_client
        self._events = events
        self._repo_manager = repo_manager
        self._logger = logger

    async def run(self) -> SolitaryResult:
        """Run the monkey and return its results.

        Returns
        -------
        SolitaryResult
            Result of monkey run.
        """
        user = await self._gafaelfawr.create_service_token(
            self._config.user, self._config.scopes
        )
        monkey = Monkey(
            name=f"solitary-{user.username}",
            business_config=self._config.business,
            user=user,
            http_client=self._http_client,
            events=self._events,
            repo_manager=self._repo_manager,
            logger=self._logger,
        )
        error = await monkey.run_once()
        return SolitaryResult(
            success=error is None,
            error=error,
            log=Path(monkey.logfile()).read_text(),
        )
