from typing import override

from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.notebookrunnerlist import NotebookRunnerListOptions
from ...models.user import AuthenticatedUser
from ...services.repo import RepoManager
from .notebookrunner import ExecutionIteration, NotebookRunner

__all__ = ["NotebookRunnerList"]


class NotebookRunnerList(NotebookRunner):
    """A notebook runner that refreshes JupyterLab sessions (and optionally
    deletes the labs) after a list of notebooks has been executed.

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
        options: NotebookRunnerListOptions,
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
        self._notebooks_to_run = options.notebooks_to_run

    @override
    def execution_iterator(self) -> ExecutionIteration:
        size = len(self._notebooks.runnable)
        return ExecutionIteration(
            iterator=iter(range(size)),
            size=size,
        )
