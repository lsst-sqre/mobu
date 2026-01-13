"""A flock of monkeys doing business."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from itertools import batched

from aiojobs import Scheduler
from httpx import AsyncClient
from rubin.repertoire import DiscoveryClient
from structlog.stdlib import BoundLogger

from ..events import Events
from ..exceptions import MonkeyNotFoundError
from ..models.business.notebookrunnercounting import (
    NotebookRunnerCountingConfig,
    NotebookRunnerCountingOptions,
)
from ..models.flock import FlockConfig, FlockData, FlockSummary
from ..models.user import AuthenticatedUser, User, UserSpec
from ..services.repo import RepoManager
from ..storage.gafaelfawr import GafaelfawrStorage
from .monkey import Monkey

__all__ = ["Flock"]


class Flock:
    """Container for a group of monkeys all running the same business.

    Parameters
    ----------
    flock_config
        Configuration for this flock of monkeys.
    replica_count
        The number of running mobu instances.
    replica_index
        The index of this replica in the StatefulSet.
    scheduler
        Job scheduler used to manage the tasks for the monkeys.
    gafaelfawr_storage
        Gafaelfawr storage client.
    discovery_client
        Shared service discovery client.
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
        flock_config: FlockConfig,
        replica_count: int,
        replica_index: int,
        scheduler: Scheduler,
        gafaelfawr_storage: GafaelfawrStorage,
        discovery_client: DiscoveryClient,
        http_client: AsyncClient,
        events: Events,
        repo_manager: RepoManager,
        logger: BoundLogger,
    ) -> None:
        self.name = flock_config.name
        self._config = flock_config
        self._replica_count = replica_count
        self._replica_index = replica_index
        self._scheduler = scheduler
        self._gafaelfawr = gafaelfawr_storage
        self._discovery = discovery_client
        self._http_client = http_client
        self._events = events
        self._repo_manager = repo_manager
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

        # Start in staggered batches
        if self._config.start_batch_size and self._config.start_batch_wait:
            # start_batch_size is the number of monkeys that should be started
            # concurrently across ALL replicas, so we should only start our
            # share of the batch.
            size = int(self._config.start_batch_size / self._replica_count)
            wait_secs = self._config.start_batch_wait.total_seconds()
            batches = list(batched(self._monkeys.values(), size, strict=False))
            num = len(batches)
            for i in range(num):
                batch = batches[i]
                logger = self._logger.bind(
                    current_batch=i + 1,
                    num_batches=num,
                    monkeys_in_batch=len(batch),
                )
                logger.info("starting batch")
                tasks = [monkey.start(self._scheduler) for monkey in batch]
                await asyncio.gather(*tasks)

                # Don't wait after starting the last batch
                if i < num - 1:
                    logger.info("pausing for batch", wait_secs=wait_secs)
                    await asyncio.sleep(wait_secs)

        # Start all at the same time
        else:
            tasks = [
                monkey.start(self._scheduler)
                for monkey in self._monkeys.values()
            ]
            await asyncio.gather(*tasks)

        self._start_time = datetime.now(tz=UTC)

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
                business=NotebookRunnerCountingConfig(
                    options=NotebookRunnerCountingOptions(
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
            discovery_client=self._discovery,
            http_client=self._http_client,
            events=self._events,
            repo_manager=self._repo_manager,
            logger=self._logger,
        )

    async def _create_users(self) -> list[AuthenticatedUser]:
        """Create the authenticated users the monkeys will run as."""
        users = self._config.users
        if not users:
            if not self._config.user_spec:
                raise RuntimeError("Neither users nor user_spec set")
            count = self._config.count
            users = self._users_from_spec(
                spec=self._config.user_spec, count=count
            )

        # We only want to run monkeys with our portion of the users, divided as
        # equaly as possible among all replicas.
        replica_index = self._replica_index
        replica_count = self._replica_count
        users = [
            user
            for i, user in enumerate(users)
            if i % replica_count == replica_index
        ]
        scopes = self._config.scopes
        coros = [
            self._gafaelfawr.create_service_token(u, scopes) for u in users
        ]

        # Gafaelfawr has to add database rows for each token to the same
        # table, so the amount of effective parallelization is limited.
        # Perform the user creation in a fixed-size batch so that we get some
        # speed-up without just piling up Gafaelfawr tasks waiting for
        # database transactions.
        results = []
        for batch in batched(coros, 10, strict=False):
            results.extend(await asyncio.gather(*batch))
        return results

    def _users_from_spec(self, *, spec: UserSpec, count: int) -> list[User]:
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
            user = User(
                username=username,
                uidnumber=uid,
                gidnumber=gid,
                groups=spec.groups,
            )
            users.append(user)
        return users
