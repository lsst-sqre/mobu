"""Models for the NotebookRunnerCounting monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .notebookrunner import NotebookRunnerOptions

__all__ = [
    "NotebookRunnerCountingConfig",
    "NotebookRunnerCountingOptions",
]


class NotebookRunnerCountingOptions(NotebookRunnerOptions):
    """Options to specify a fixed number of notebooks to run per session."""

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            " NotebookRunnerCounting goes through the directory of notebooks"
            " one-by-one, running the entirety of each one and starting"
            " again at the beginning of the list when it runs out, until"
            " it has executed a total of `max_executions` notebooks. It then"
            " closes the session (and optionally deletes and recreates the"
            " lab, controlled by `delete_lab`), and then picks up where it"
            " left off."
        ),
        examples=[25],
        ge=1,
    )


class NotebookRunnerCountingConfig(BusinessConfig):
    """Configuration specialization for NotebookRunner."""

    type: Literal["NotebookRunnerCounting"] = Field(
        ..., title="Type of business to run"
    )

    options: NotebookRunnerCountingOptions = Field(
        default_factory=NotebookRunnerCountingOptions,
        title="Options for the monkey business",
    )
