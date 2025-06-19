"""Shared models for different notebook runners."""

from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from safir.pydantic import HumanTimedelta

from ...constants import NOTEBOOK_REPO_BRANCH, NOTEBOOK_REPO_URL
from ...models.business.nublado import (
    NubladoBusinessData,
    NubladoBusinessOptions,
)

__all__ = [
    "NotebookFilterResults",
    "NotebookMetadata",
    "NotebookRunnerData",
    "NotebookRunnerOptions",
]


class CollectionRule(BaseModel):
    """A set of patterns to filter the list of notebooks to run in a repo."""

    type: Literal["include", "exclude"] = Field(
        title="Collection rule type",
        description=(
            "'include' will gather all notebooks matched by any pattern."
            " 'exclude' will not run any notebook matched by any pattern"
        ),
    )

    patterns: set[str] = Field(
        title="patterns",
        description=(
            "A set of Python pathlib glob patterns:"
            " https://docs.python.org/3/library/pathlib.html#pattern-language"
            " This rule will gather all of the notebooks matched by any"
            " pattern in this list to either include or exclude."
        ),
    )


class Filterable(BaseModel):
    """Mixin for config to specify patterns for which notebooks to run."""

    exclude_dirs: set[Path] = Field(
        set(),
        title="Any notebooks in these directories will not be run",
        description=(
            "DEPRECATED: use collection_rules instead. If both exclude_dirs"
            " and collection_rules are set, exclude_dirs will be added as"
            " exclude rules to the collection_rules. These directories are"
            " relative to the repo root. Any notebooks in child directories"
            " of these directories will also be excluded. Only used by the"
            " NotebookRunner businesses."
        ),
        examples=["some-dir", "some-dir/some-other-dir"],
    )

    collection_rules: list[CollectionRule] = Field(
        [],
        title="Collection rules",
        description=(
            "A set of rules describing which notebooks in a repo to run. Only"
            " used by NotebookRunner businesses."
        ),
    )


class NotebookRunnerOptions(NubladoBusinessOptions, Filterable):
    """Options for all types NotebookRunner monkey business."""

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

    notebook_idle_time: HumanTimedelta = Field(
        timedelta(seconds=0),
        title="How long to wait between notebook executions",
        description="Used by NotebookRunner businesses",
        examples=["30s"],
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


class NotebookMetadata(BaseModel):
    """Notebook metadata that we care about."""

    required_services: set[str] = Field(
        set(),
        title="Required services",
        description=(
            "The names of services that the platform is required to provide in"
            " order for the notebook to run correctly. Not all environments"
            " provide all services."
        ),
        examples=[{"tap", "ssotap", "butler"}],
    )


class NotebookFilterResults(BaseModel):
    """Valid notebooks and categories for invalid notebooks."""

    all: set[Path] = Field(
        default=set(),
        title="All notebooks",
        description="All notebooks in the repository",
    )

    runnable: set[Path] = Field(
        default=set(),
        title="Runnable notebooks",
        description=(
            "These are the notebooks to run after all filtering has been done"
        ),
    )

    excluded_by_dir: set[Path] = Field(
        default=set(),
        title="Excluded by directory",
        description=(
            "These notebooks won't be run because they are in a directory that"
            "is excliticly excluded"
        ),
    )

    excluded_by_service: set[Path] = Field(
        default=set(),
        title="Excluded by service availability",
        description=(
            "These notebooks won't be run because the depend on services which"
            " are not available in this environment"
        ),
    )
