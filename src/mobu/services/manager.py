"""Manager for all the running flocks."""

from __future__ import annotations

import asyncio

from aiojobs import Scheduler
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ..dependencies.config import config_dependency
from ..events import Events
from ..exceptions import FlockNotFoundError
from ..models.flock import FlockConfig, FlockSummary
from ..services.repo import RepoManager
from ..storage.gafaelfawr import GafaelfawrStorage
from .flock import Flock

__all__ = ["FlockManager"]


class FlockManager:
    """Manages all of the running flocks.

    This should be a process singleton. It is responsible for managing all of
    the flocks running in the background, including shutting them down and
    starting new ones.

    Parameters
    ----------
    gafaelfawr_storage
        Gafaelfawr storage client.
    http_client
        Shared HTTP client.
    events
        Event publishers.
    repo_manager
        For efficiently cloning git repos.
    logger
        Global logger to use for process-wide (not monkey) logging.
    """

    def __init__(
        self,
        *,
        gafaelfawr_storage: GafaelfawrStorage,
        http_client: AsyncClient,
        events: Events,
        repo_manager: RepoManager,
        logger: BoundLogger,
    ) -> None:
        self._config = config_dependency.config
        self._gafaelfawr = gafaelfawr_storage
        self._http_client = http_client
        self._events = events
        self._repo_manager = repo_manager
        self._logger = logger
        self._flocks: dict[str, Flock] = {}
        self._scheduler = Scheduler(limit=None, pending_limit=0)

    async def aclose(self) -> None:
        """Stop all flocks and free all resources."""
        awaits = [self.stop_flock(f) for f in self._flocks]
        await asyncio.gather(*awaits)
        await self._scheduler.close()

    async def autostart(self) -> None:
        """Automatically start configured flocks.

        This function should be called from the startup hook of the FastAPI
        application.
        """
        for flock_config in self._config.autostart:
            await self.start_flock(flock_config)

    async def start_flock(self, flock_config: FlockConfig) -> Flock:
        """Create and start a new flock of monkeys.

        Parameters
        ----------
        flock_config
            Configuration for that flock.

        Returns
        -------
        Flock
            Newly-created flock.
        """
        flock = Flock(
            flock_config=flock_config,
            replica_count=self._config.replica_count,
            instance_id=self._config.instance_id,
            scheduler=self._scheduler,
            gafaelfawr_storage=self._gafaelfawr,
            http_client=self._http_client,
            events=self._events,
            repo_manager=self._repo_manager,
            logger=self._logger,
        )
        if flock.name in self._flocks:
            await self._flocks[flock.name].stop()
        self._flocks[flock.name] = flock
        await flock.start()
        return flock

    def get_flock(self, name: str) -> Flock:
        """Retrieve a flock by name.

        Parameters
        ----------
        name
            Name of the flock.

        Returns
        -------
        Flock
            Flock with that name.

        Raises
        ------
        FlockNotFoundError
            Raised if no flock was found with that name.
        """
        flock = self._flocks.get(name)
        if flock is None:
            raise FlockNotFoundError(name)
        return flock

    def list_flocks_for_repo(self, repo_url: str, repo_ref: str) -> list[str]:
        return [
            name
            for name, flock in self._flocks.items()
            if flock.uses_repo(repo_url=repo_url, repo_ref=repo_ref)
        ]

    def list_flocks(self) -> list[str]:
        """List all flocks.

        Returns
        -------
        list of str
            Names of all flocks in sorted order.
        """
        return sorted(self._flocks.keys())

    def summarize_flocks(self) -> list[FlockSummary]:
        """Summarize the status of all flocks.

        Returns
        -------
        list of FlockSumary
            Flock summary data sorted by flock name.
        """
        return [f.summary() for _, f in sorted(self._flocks.items())]

    async def stop_flock(self, name: str) -> None:
        """Stop a flock.

        Parameters
        ----------
        name
            Name of flock to stop.

        Raises
        ------
        FlockNotFoundError
            Raised if no flock was found with that name.
        """
        flock = self._flocks.get(name)
        if flock is None:
            raise FlockNotFoundError(name)
        del self._flocks[name]
        await flock.stop()

    def refresh_flock(self, name: str) -> None:
        """Tell a flock to refresh.

        Parameters
        ----------
        name
            Name of flock to refresh.

        Raises
        ------
        FlockNotFoundError
            Raised if no flock was found with that name.
        """
        flock = self._flocks.get(name)
        if flock is None:
            raise FlockNotFoundError(name)
        flock.signal_refresh()
