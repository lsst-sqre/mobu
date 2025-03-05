from typing import override

from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.notebookrunnercounting import (
    NotebookRunnerCountingOptions,
)
from ...models.user import AuthenticatedUser
from ...services.repo import RepoManager
from .notebookrunner import ExecutionIteration, NotebookRunner

__all__ = ["NotebookRunnerCounting"]


class NotebookRunnerCounting(NotebookRunner):
    """A notebook runner that refreshes JupyterLab sessions (and optionally
    deletes the labs) after a configurable number of executions.

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
        options: NotebookRunnerCountingOptions,
        user: AuthenticatedUser,
        repo_manager: RepoManager,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            repo_manager=repo_manager,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._max_executions = options.max_executions

    @override
    def execution_iterator(self) -> ExecutionIteration:
        return ExecutionIteration(
            iterator=iter(range(self._max_executions)),
            size=self._max_executions,
        )
