"""GitHub CI checks for notebook repos."""

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.notebookrunner import (
    CollectionRule,
    NotebookRunnerOptions,
)
from ...models.business.notebookrunnerlist import NotebookRunnerListConfig
from ...models.ci_manager import CiJobSummary
from ...models.solitary import SolitaryConfig
from ...models.user import User
from ...services.repo import RepoManager
from ...services.solitary import Solitary
from ...storage.gafaelfawr import GafaelfawrStorage
from ...storage.github import CheckRun, GitHubStorage


class CiNotebookJob:
    """Runs changed notebooks and updates a GitHub CI check.

    Parameters
    ----------
    github_storage:
        GitHub storage client.
    check_run:
        A GitHub storage check run.
    http_client:
        Shared HTTP client.
    events:
        Event publishers.
    gafaelfawr_storage:
        Gafaelfawr storage client.
    logger:
        Context logger.

    """

    def __init__(
        self,
        github_storage: GitHubStorage,
        check_run: CheckRun,
        http_client: AsyncClient,
        events: Events,
        repo_manager: RepoManager,
        gafaelfawr_storage: GafaelfawrStorage,
        logger: BoundLogger,
    ) -> None:
        self._github = github_storage
        self.check_run = check_run
        self._http_client = http_client
        self._events = events
        self._repo_manager = repo_manager
        self._gafaelfawr = gafaelfawr_storage
        self._logger = logger.bind(ci_job_type="NotebookJob")

    async def run(self, user: User, scopes: list[str]) -> None:
        """Run all relevant changed notebooks and report back to GitHub.

        Run only changed notebooks that aren't excluded in the mobu config
        file in the repo.  If there is no mobu config file, then don't exclude
        any changed notebooks.
        """
        # Get changed notebook files
        files = await self._github.get_pr_files()

        notebooks = [file for file in files if file.suffix == ".ipynb"]

        # Don't do anything if there are no notebooks to run
        if not bool(notebooks):
            await self.check_run.succeed(
                details="No changed notebooks to run.",
            )
            return

        # Run notebooks using a Solitary runner
        summary = "Running these notebooks via Mobu:\n" + "\n".join(
            [f"* {notebook}" for notebook in notebooks]
            + [
                "Note that not all of these may run. Some may be exluded based"
                " on config in the repo:"
                " https://mobu.lsst.io/user-guide/in-repo-config.html"
            ]
        )
        await self.check_run.start(summary=summary)
        solitary_config = SolitaryConfig(
            user=user,
            scopes=[str(scope) for scope in scopes],
            business=NotebookRunnerListConfig(
                type="NotebookRunnerList",
                options=NotebookRunnerOptions(
                    repo_ref=self._github.ref,
                    repo_url=f"https://github.com/{self._github.repo_owner}/{self._github.repo_name}.git",
                    collection_rules=[
                        CollectionRule(
                            type="intersect_union_of",
                            patterns={str(notebook) for notebook in notebooks},
                        )
                    ],
                ),
            ),
        )
        solitary = Solitary(
            solitary_config=solitary_config,
            gafaelfawr_storage=self._gafaelfawr,
            http_client=self._http_client,
            events=self._events,
            repo_manager=self._repo_manager,
            logger=self._logger,
        )

        result = await solitary.run()
        if result.success:
            await self.check_run.succeed()
        else:
            await self.check_run.fail(error=result.error or "Unknown Error")

    def summarize(self) -> CiJobSummary:
        """Information about this job."""
        return CiJobSummary.model_validate(
            {"commit_url": self._github.commit_url}
        )
