"""Models for the NotebookRunnerList monkey business."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from ...models.business.base import BusinessConfig
from .notebookrunner import NotebookRunnerOptions

__all__ = [
    "NotebookRunnerListConfig",
    "NotebookRunnerListOptions",
]


class NotebookRunnerListOptions(NotebookRunnerOptions):
    """Specify a list of notebooks to run in a single lab session."""

    notebooks_to_run: list[Path] = Field(
        [],
        title="Specific notebooks to run",
        description=("Only these specific notebooks will be executed."),
    )


class NotebookRunnerListConfig(BusinessConfig):
    """Configuration specialization for NotebookRunnerList."""

    type: Literal["NotebookRunnerList"] = Field(
        ..., title="Type of business to run"
    )

    options: NotebookRunnerListOptions = Field(
        default_factory=NotebookRunnerListOptions,
        title="Options for the monkey business",
    )
