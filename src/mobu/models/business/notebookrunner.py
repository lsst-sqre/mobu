"""Models for the NotebookRunner monkey business."""

from __future__ import annotations

from typing import Literal, Optional

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
        example=25,
        ge=1,
    )

    repo_branch: str = Field(
        NOTEBOOK_REPO_BRANCH,
        title="Git branch of notebook repository to execute",
        description="Only used by the NotebookRunner",
    )

    repo_url: str = Field(
        NOTEBOOK_REPO_URL,
        title="Git URL of notebook repository to execute",
        description="Only used by the NotebookRunner",
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

    notebook: Optional[str] = Field(
        None,
        title="Name of the currently running notebook",
        description="Will not be present if no notebook is being executed",
        example="cluster.ipynb",
    )

    running_code: Optional[str] = Field(
        None,
        title="Currently running code",
        description="Will not be present if no code is being executed",
        example='import json\nprint(json.dumps({"foo": "bar"})\n',
    )
