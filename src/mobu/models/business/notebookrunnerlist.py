"""Models for the NotebookRunnerList monkey business."""

from typing import Literal

from pydantic import Field

from ...models.business.base import BusinessConfig
from .notebookrunner import NotebookRunnerOptions

__all__ = [
    "NotebookRunnerListConfig",
]


class NotebookRunnerListConfig(BusinessConfig):
    """Configuration specialization for NotebookRunnerList."""

    type: Literal["NotebookRunnerList"] = Field(
        ..., title="Type of business to run"
    )

    options: NotebookRunnerOptions = Field(
        default_factory=NotebookRunnerOptions,
        title="Options for the monkey business",
    )
