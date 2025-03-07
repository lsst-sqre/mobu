"""Models for the NotebookRunnerInfinite monkey business."""

from typing import Literal

from pydantic import Field

from ...models.business.base import BusinessConfig
from .notebookrunner import NotebookRunnerOptions

__all__ = [
    "NotebookRunnerInfiniteConfig",
]


class NotebookRunnerInfiniteConfig(BusinessConfig):
    """Configuration specialization for NotebookRunner."""

    type: Literal["NotebookRunnerInfinite"] = Field(
        ..., title="Type of business to run"
    )

    options: NotebookRunnerOptions = Field(
        default_factory=NotebookRunnerOptions,
        title="Options for the monkey business",
    )
