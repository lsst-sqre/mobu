"""Models for the NotebookRunner monkey business."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from ...constants import NOTEBOOK_REPO_BRANCH, NOTEBOOK_REPO_URL
from .base import BusinessConfig
from .nublado import NubladoBusinessData, NubladoBusinessOptions

__all__ = [
    "NotebookRunnerConfig",
    "NotebookRunnerData",
    "NotebookRunnerOptions",
]


class NotebookRunnerOptions(NubladoBusinessOptions):
    """Options for NotebookRunner monkey business."""

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            " NotebookRunner goes through the directory of notebooks"
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

    repo_ref: str = Field(
        NOTEBOOK_REPO_BRANCH,
        title="Git ref of notebook repository to execute",
        description="Only used by the NotebookRunner",
        examples=["main", "03cd564dd2025bf17054d9ebfeeb5c5a266e3484"],
    )

    repo_url: str = Field(
        NOTEBOOK_REPO_URL,
        title="Git URL of notebook repository to execute",
        description="Only used by the NotebookRunner",
    )

    notebooks_to_run: list[Path] = Field(
        [],
        title="Specific notebooks to run",
        description=(
            "If this is set, then only these specific notebooks will be"
            " executed."
        ),
    )

    exclude_dirs: set[Path] = Field(
        set(),
        title="Any notebooks in these directories will not be run",
        description=(
            " These directories are relative to the repo root. Any notebooks"
            " in child directories of these directories will also be excluded."
            " Only used by the NotebookRunner."
        ),
        examples=["some-dir", "some-dir/some-other-dir"],
    )


class NotebookRunnerConfig(BusinessConfig):
    """Configuration specialization for NotebookRunner."""

    type: Literal["NotebookRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: NotebookRunnerOptions = Field(
        default_factory=NotebookRunnerOptions,
        title="Options for the monkey business",
    )


class NotebookRunnerData(NubladoBusinessData):
    """Status of a running NotebookRunner business."""

    notebook: str | None = Field(
        None,
        title="Name of the currently running notebook",
        description="Will not be present if no notebook is being executed",
        examples=["cluster.ipynb"],
    )

    running_code: str | None = Field(
        None,
        title="Currently running code",
        description="Will not be present if no code is being executed",
        examples=['import json\nprint(json.dumps({"foo": "bar"})\n'],
    )
