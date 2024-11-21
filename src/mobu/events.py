"""App metrics events."""

from datetime import timedelta
from typing import override

from safir.dependencies.metrics import EventDependency, EventMaker
from safir.metrics import EventManager, EventPayload


class EventBase(EventPayload):
    """Attributes on every mobu event."""

    flock: str | None
    business: str
    username: str


class NotebookBase(EventBase):
    """Attributes for all notebook-related events."""

    notebook: str
    repo: str
    repo_ref: str


class NotebookExecution(NotebookBase):
    """Reported after a notebook is finished executing."""

    duration: timedelta | None
    success: bool


class NotebookCellExecution(NotebookBase):
    """Reported after a notebook cell is finished executing."""

    duration: timedelta | None
    cell_id: str
    success: bool
    contents: str


class NubladoPythonExecution(EventBase):
    """Reported after a notebook cell is finished executing."""

    duration: timedelta | None
    success: bool
    code: str


class GitLfsCheck(EventBase):
    """Reported from Git LFS businesses."""

    success: bool
    duration_total: timedelta | None = None
    duration_create_origin_repo: timedelta | None = None
    duration_populate_origin_repo: timedelta | None = None
    duration_create_checkout_repo: timedelta | None = None
    duration_add_lfs_assets: timedelta | None = None
    duration_add_credentials: timedelta | None = None
    duration_push_lfs_tracked_assets: timedelta | None = None
    duration_remove_git_credentials: timedelta | None = None
    duration_verify_origin_contents: timedelta | None = None
    duration_create_clone_repo: timedelta | None = None
    duration_verify_asset_contents: timedelta | None = None
    duration_install_lfs_to_repo: timedelta | None = None
    duration_add_lfs_data: timedelta | None = None
    duration_git_attribute_installation: timedelta | None = None


class TapQuery(EventBase):
    """Reported when a TAP query is executed."""

    success: bool
    duration: timedelta | None
    sync: bool
    query: str


class Events(EventMaker):
    """Container for app metrics event publishers."""

    @override
    async def initialize(self, manager: EventManager) -> None:
        self.tap_query = await manager.create_publisher("tap_query", TapQuery)
        self.git_lfs_check = await manager.create_publisher(
            "git_lfs_check", GitLfsCheck
        )
        self.notebook_execution = await manager.create_publisher(
            "notebook_execution", NotebookExecution
        )
        self.notebook_cell_execution = await manager.create_publisher(
            "notebook_cell_execution", NotebookCellExecution
        )
        self.nublado_python_execution = await manager.create_publisher(
            "nublado_python_execution", NubladoPythonExecution
        )


# We'll call .initalize on this in our app start up
events_dependency = EventDependency(Events())
