"""A flock of monkeys doing business."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime

from aiojobs import Scheduler
from httpx import AsyncClient
from safir.datetime import current_datetime
from structlog.stdlib import BoundLogger

from ..exceptions import MonkeyNotFoundError
from ..models.business.notebookrunner import (
    NotebookRunnerConfig,
    NotebookRunnerOptions,
)
from ..models.flock import FlockConfig, FlockData, FlockSummary
from ..models.user import AuthenticatedUser, User, UserSpec
from ..storage.gafaelfawr import GafaelfawrStorage
from .monkey import Monkey

__all__ = ["Flock"]


class Flock:
    """Container for a group of monkeys all running the same business.

    Parameters
    ----------
    flock_config
        Configuration for this flock of monkeys.
    scheduler
        Job scheduler used to manage the tasks for the monkeys.
    gafaelfawr_storage
        Gafaelfawr storage client.
    http_client
        Shared HTTP client.
    logger
        Global logger.
    """

    def __init__(
        self,
        *,
        flock_config: FlockConfig,
        scheduler: Scheduler,
        gafaelfawr_storage: GafaelfawrStorage,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        self.name = flock_config.name
        self._config = flock_config
        self._scheduler = scheduler
        self._gafaelfawr = gafaelfawr_storage
        self._http_client = http_client
        self._logger = logger.bind(flock=self.name)
        self._monkeys: dict[str, Monkey] = {}
        self._start_time: datetime | None = None

    def dump(self) -> FlockData:
        """Return information about all running monkeys."""
        return FlockData(
            name=self._config.name,
            config=self._config,
            monkeys=[m.dump() for m in self._monkeys.values()],
        )

    def get_monkey(self, name: str) -> Monkey:
        """Retrieve a given monkey by name.

        Parameters
        ----------
        name
            Name of monkey to return.

        Returns
        -------
        Monkey
            Requested monkey.

        Raises
        ------
        MonkeyNotFoundError
            Raised if no monkey was found with that name.
        """
        monkey = self._monkeys.get(name)
        if not monkey:
            raise MonkeyNotFoundError(name)
        return monkey

    def list_monkeys(self) -> list[str]:
        """List the names of the monkeys."""
        return sorted(self._monkeys.keys())

    def summary(self) -> FlockSummary:
        """Return summary statistics about the flock."""
        count = 0
        successes = 0
        failures = 0
        for monkey in self._monkeys.values():
            count += 1
            successes += monkey.business.success_count
            failures += monkey.business.failure_count
        return FlockSummary(
            name=self.name,
            business=self._config.business.type,
            start_time=self._start_time,
            monkey_count=count,
            success_count=successes,
            failure_count=failures,
        )

    async def start(self) -> None:
        """Start all the monkeys."""
        self._logger.info("Creating users")
        users = await self._create_users()
        self._logger.info("Starting flock")
        for user in users:
            monkey = self._create_monkey(user)
            self._monkeys[user.username] = monkey
            await monkey.start(self._scheduler)
        self._start_time = current_datetime(microseconds=True)

    async def stop(self) -> None:
        """Stop all the monkeys.

        Stopping a monkey can require waiting for a timeout from JupyterHub if
        it were in the middle of spawning, so stop them all in parallel to
        avoid waiting for the sum of all timeouts.
        """
        self._logger.info("Stopping flock")
        awaits = [m.stop() for m in self._monkeys.values()]
        await asyncio.gather(*awaits)

    def signal_refresh(self) -> None:
        """Signal all the monkeys to refresh their busniess."""
        self._logger.info("Signaling monkeys to refresh")
        for monkey in self._monkeys.values():
            monkey.signal_refresh()

    def uses_repo(self, repo_url: str, repo_ref: str) -> bool:
        match self._config:
            case FlockConfig(
                business=NotebookRunnerConfig(
                    options=NotebookRunnerOptions(
                        repo_url=url,
                        repo_ref=branch,
                    )
                )
            ) if (url, branch) == (repo_url, repo_ref):
                return True
        return False

    def _create_monkey(self, user: AuthenticatedUser) -> Monkey:
        """Create a monkey that will run as a given user."""
        return Monkey(
            name=user.username,
            flock=self.name,
            business_config=self._config.business,
            user=user,
            http_client=self._http_client,
            logger=self._logger,
        )

    async def _create_users(self) -> list[AuthenticatedUser]:
        """Create the authenticated users the monkeys will run as."""
        users = self._config.users
        if not users:
            if not self._config.user_spec:
                raise RuntimeError("Neither users nor user_spec set")
            count = self._config.count
            users = self._users_from_spec(self._config.user_spec, count)
        scopes = self._config.scopes
        return [
            await self._gafaelfawr.create_service_token(u, scopes)
            for u in users
        ]

    def _users_from_spec(self, spec: UserSpec, count: int) -> list[User]:
        """Generate count Users from the provided spec."""
        padding = int(math.log10(count) + 1)
        users = []
        for i in range(1, count + 1):
            username = spec.username_prefix + str(i).zfill(padding)
            if spec.uid_start is not None:
                uid = spec.uid_start + i - 1
            else:
                uid = None
            if spec.gid_start is not None:
                gid = spec.gid_start + i - 1
            else:
                gid = None
            user = User(username=username, uidnumber=uid, gidnumber=gid)
            users.append(user)
        return users
