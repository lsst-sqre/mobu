"""Execute a list of notebooks in a single JupyterLab session."""

from typing import override

from rubin.repertoire import DiscoveryClient
from structlog.stdlib import BoundLogger

from ...events import Events
from ...models.business.notebookrunner import NotebookRunnerOptions
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
    discovery_client
        Service discovery client.
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
        options: NotebookRunnerOptions,
        user: AuthenticatedUser,
        discovery_client: DiscoveryClient,
        repo_manager: RepoManager,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            repo_manager=repo_manager,
            discovery_client=discovery_client,
            events=events,
            logger=logger,
            flock=flock,
        )

    @override
    def execution_iterator(self) -> ExecutionIteration:
        """Return an iterator counts the number of specified notebooks."""
        size = len(self._notebooks)
        return ExecutionIteration(
            iterator=iter(range(size)),
            size=size,
        )
