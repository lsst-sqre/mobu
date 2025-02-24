"""Manager for background workers that process work from GitHub checks."""

from __future__ import annotations

import asyncio
from asyncio import Queue
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from aiojobs import Job, Scheduler
from httpx import AsyncClient
from safir.github import GitHubAppClientFactory
from structlog.stdlib import BoundLogger

from ...dependencies.config import config_dependency
from ...events import Events
from ...models.ci_manager import CiManagerSummary, CiWorkerSummary
from ...models.user import User
from ...services.repo import RepoManager
from ...storage.gafaelfawr import GafaelfawrStorage
from ...storage.github import GitHubStorage
from .ci_notebook_job import CiNotebookJob

__all__ = ["CiManager"]


@dataclass
class CiManagerLifecycle:
    marked_remaining: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class JobLifecycle:
    processing: asyncio.Event = field(default_factory=asyncio.Event)
    processed: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class QueuedJob:
    job: CiNotebookJob
    lifecycle: JobLifecycle


QueueItem: TypeAlias = QueuedJob | Literal["stop"]


class CiManager:
    """Manages processing work for GitHub CI checks.

    This should be a process singleton. It is responsible for:
    * Creating background workers to process GitHub CI events
    * Ensuring they run at the appropriate level of concurrency given the
      number of available users
    * Ensuring GitHub CI checks are not left in a forever-in-progress state
      when mobu shuts down

    Parameters
    ----------
    users
        A list of static users that are available to run jobs. Each of these
        users will get assigned to a worker, and will process one job at a
        time.
    http_client
        Shared HTTP client.
    gafaelfawr_storage
        Gafaelfawr storage client.
    events
        Event publishers.
    logger
        Global logger to use for process-wide (not monkey) logging.
    """

    shutdown_error_msg = "Mobu stopped, try re-running this check."

    def __init__(
        self,
        github_app_id: int,
        github_private_key: str,
        scopes: list[str],
        users: list[User],
        http_client: AsyncClient,
        events: Events,
        repo_manager: RepoManager,
        gafaelfawr_storage: GafaelfawrStorage,
        logger: BoundLogger,
    ) -> None:
        self._config = config_dependency.config
        self._scopes = scopes
        self._users = users
        self._gafaelfawr = gafaelfawr_storage
        self._http_client = http_client
        self._events = events
        self._repo_manager = repo_manager
        self._logger = logger.bind(ci_manager=True)
        self._scheduler: Scheduler = Scheduler()
        self._queue: Queue[QueueItem] = Queue()
        self._jobs: list[Job] = []
        self.workers: list[Worker] = []

        # Used for deterministic testing
        self.lifecycle = CiManagerLifecycle()

        self._factory = GitHubAppClientFactory(
            id=github_app_id,
            key=github_private_key,
            name="lsst-sqre/mobu CI app",
            http_client=http_client,
        )

    async def start(self) -> None:
        """Start the workers for the CI manager."""
        self._logger.info("Starting CI manager...")
        self.workers = [
            Worker(
                user=user,
                scopes=self._scopes,
                queue=self._queue,
                logger=self._logger,
            )
            for user in self._users
        ]
        self._jobs = [
            await self._scheduler.spawn(worker.run())
            for worker in self.workers
        ]
        self._logger.info("CI manager started")

    async def aclose(self) -> None:
        """Stop the workers and update GitHub CI checks for pending work.

        We initially fail in-progress jobs too because we don't want any GitHub
        check runs to be forever in-progress if mobu gets killed before they
        finish. If they do end up finishing in time, then they'll be
        re-concluded as successful.

        We'd rather have false-negative GitHub checks than forever-in-progress
        checks, because:
        * There is no way to re-run in-progress checks from the GitHub UI
        * There is no way to know for sure from the GitHub UI that a check
          will never be concluded.

        A failed check can easily be re-run by any user, so this is an
        acceptable tradeoff, assuming false-negatives happen infrequently.

        Scenarios:

        ### Job completes

        1. Mobu is told to shut down
        2. Mobu tells GitHub that job has failed due to restart
        3. Job finishes before mobu is SIGKILLed
        4. Mobu tells GitHub that job is successful
        5. Mobu is SIGKILLed or exits cleanly

        Result: GitHub check run displays success, which is corrcect.
                An incorrect failure status will have been displayed for a
                brief period of time.
        User action needed: None

        ### Job does not complete

        1. Mobu is told to shut down
        2. Mobu tells GitHub that job has failed due to restart
        3. Mobu is SIGKILLed

        Result: GitHub check run displays failure status, which is correct.
        User action needed: Re-run check in GitHub UI

        ### Job completes, but mobu is killed before it can tell GitHub

        This situation should be pretty rare.
        1. Mobu is told to shut down
        2. Mobu tells GitHub that job has failed due to restart
        3. Job finishes before mobu is SIGKILLed
        4. Mobu is SIGKILLed before it can tell GitHub the job has succeeded

        Result: GitHub check run displays failure status, which is incorrect.
        User action needed: Re-run check in GitHub UI
        """
        self._logger.info("Stopping CI manager...")

        # Tell workers with in-progress jobs to stop after their current job
        for worker in self.workers:
            worker.stop()

        # Tell GitHub all checks for in progress jobs are failed in case we
        # shutdown uncleanly
        awaits = [
            worker.current_job.check_run.fail(error=self.shutdown_error_msg)
            for worker in self.workers
            if worker.current_job is not None
        ]
        await asyncio.gather(*awaits)

        # Tell GitHub all checks queued are failed
        awaits = []
        while not self._queue.empty():
            item = await self._queue.get()
            if item != "stop":
                awaits.append(
                    item.job.check_run.fail(error=self.shutdown_error_msg)
                )
        await asyncio.gather(*awaits)
        self.lifecycle.marked_remaining.set()

        # Tell workers listening on a currently empty queue to stop
        for _ in self.workers:
            await self._queue.put("stop")

        # Wait for workers to finish any in-progress jobs
        for job in self._jobs:
            await job.wait()

        await self._scheduler.close()
        self._logger.info("CI manager stopped")

    async def enqueue(
        self,
        installation_id: int,
        repo_owner: str,
        repo_name: str,
        ref: str,
        pull_number: int,
    ) -> JobLifecycle:
        """Enqueue a job to run something for a given Git repo and commit.

        Parameters
        ----------
        installation_id
            The GitHub installation ID of the app that generated this work.
        repo_owner.
            A GitHub organization name.
        repo_name
            A GitHub repo name.
        ref
            A GitHub commit SHA.
        pull_number
            The number that identifies a pull request.

        Returns
        -------
        JobLifecycle
            Only used in unit tests.

            Helpful for creating deterministic ordering scenarios when
            processing multiple jobs.
        """
        storage = await GitHubStorage.create(
            factory=self._factory,
            installation_id=installation_id,
            repo_name=repo_name,
            repo_owner=repo_owner,
            ref=ref,
            pull_number=pull_number,
        )

        check_run = await storage.create_check_run(
            name=f"Mobu ({self._config.environment_url})",
            summary="Waiting for Mobu to run...",
        )

        job = CiNotebookJob(
            github_storage=storage,
            check_run=check_run,
            http_client=self._http_client,
            events=self._events,
            repo_manager=self._repo_manager,
            logger=self._logger,
            gafaelfawr_storage=self._gafaelfawr,
        )
        lifecycle = JobLifecycle()
        await self._queue.put(QueuedJob(job=job, lifecycle=lifecycle))
        return lifecycle

    def summarize(self) -> CiManagerSummary:
        return CiManagerSummary.model_validate(
            {
                "workers": [worker.summarize() for worker in self.workers],
                "num_queued": self._queue.qsize(),
            }
        )


class Worker:
    """Run mobu work with a particular User.

    Parameters
    ----------
    scopes
        A list of Gafaelfawr scopes granted to the job's user
    user
        The user to do the work as.
    queue
        A queue to get the work from.
    logger
        The context logger.
    """

    def __init__(
        self,
        *,
        scopes: list[str],
        user: User,
        queue: Queue[QueueItem],
        logger: BoundLogger,
    ) -> None:
        self._scopes = scopes
        self._user = user
        self._queue = queue
        self._logger = logger.bind(ci_worker=user.username)
        self._stopping = False
        self._num_processed = 0

        self.current_job: CiNotebookJob | None = None

    async def run(self) -> None:
        """Pick up work from a queue until signaled to stop.

        The ``lifecycle`` logic is only used in unit tests to generate
        deterministic scenarios involving many jobs and workers.
        """
        self._logger.info("Worker started")
        while item := await self._queue.get():
            if item == "stop":
                break
            job = item.job
            lifecycle = item.lifecycle
            self.current_job = job
            lifecycle.processing.set()
            self._logger.info(
                f"Processing job: {job}, with user: {self._user}"
            )

            await job.run(user=self._user, scopes=self._scopes)

            lifecycle.processed.set()
            self.current_job = None
            self._logger.info(f"Finished job: {job}, with user: {self._user}")
            self._num_processed += 1
            if self._stopping:
                break
        self._logger.info("Worker stopped")

    def stop(self) -> None:
        """Don't pick up any more work after finishing the current job."""
        self._stopping = True

    def summarize(self) -> CiWorkerSummary:
        """Information about this worker."""
        return CiWorkerSummary.model_validate(
            {
                "user": self._user,
                "num_processed": self._num_processed,
                "current_job": self.current_job.summarize()
                if self.current_job
                else None,
            }
        )
