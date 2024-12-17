"""App metrics events."""

from datetime import timedelta
from typing import override

from safir.dependencies.metrics import EventMaker
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
    repo_hash: str


class NotebookExecution(NotebookBase):
    """Reported after a notebook is finished executing."""

    duration: timedelta | None
    success: bool


class NotebookCellExecution(NotebookBase):
    """Reported after a notebook cell is finished executing."""

    duration: timedelta | None
    cell_id: str
    success: bool


class NubladoPythonExecution(EventBase):
    """Reported after a nublado python execution."""

    duration: timedelta | None
    success: bool
    code: str


class NubladoSpawnLab(EventBase):
    """Reported for every attempt to spawn a lab."""

    duration: timedelta
    success: bool


class NubladoDeleteLab(EventBase):
    """Reported for every attempt to delete a lab."""

    duration: timedelta
    success: bool


class GitLfsCheck(EventBase):
    """Reported from Git LFS businesses."""

    success: bool
    duration: timedelta | None = None


class TapQuery(EventBase):
    """Reported when a TAP query is executed."""

    success: bool
    duration: timedelta | None
    sync: bool


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
        self.nublado_spawn_lab = await manager.create_publisher(
            "nublado_spawn_lab", NubladoSpawnLab
        )

        self.nublado_delete_lab = await manager.create_publisher(
            "nublado_delete_", NubladoDeleteLab
        )
