"""Shared models for different notebook runners."""

from datetime import timedelta
from pathlib import Path

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


class Filterable(BaseModel):
    """Mixin for config to specify patterns for which notebooks to run."""

    exclude_dirs: set[Path] = Field(
        set(),
        title="Any notebooks in these directories will not be run",
        description=(
            "DEPRECATED: use include_patterns and exclude_patterns instead."
            " If include_patterns or exclude_patterns is set, then"
            " exclude_dirs can not be used. These directories are relative to"
            " the repo root. Any notebooks in child directories of these"
            " directories will also be excluded. Only used by the"
            " NotebookRunner businesses."
        ),
        examples=["some-dir", "some-dir/some-other-dir"],
    )

    include_patterns: set[str] = Field(
        set(),
        title="Include patterns",
        description=(
            "Notebooks that match ANY of these will be considered, but exclude"
            " patterns take precedence. If a notebook matches one of these"
            " patterns but also matches an exclude pattern, then it will not"
            " be run. Patterns are python pathlib glob patterns:"
            " https://docs.python.org/3/library/pathlib.html#pathlib-pattern-language"
            " Only used by NotebookRunner businesses."
        ),
        examples=[
            {"some/dir/some_notebook.ipynb"},
            {"some/dir/**", "**/some_prefix_*.ipynb"},
        ],
    )

    exclude_patterns: set[str] = Field(
        set(),
        title="Include patterns",
        description=(
            "Notebooks that match ANY of these pattern will NOT be run."
            " Patterns are python pathlib glob patterns:"
            " https://docs.python.org/3/library/pathlib.html#pathlib-pattern-language"
            " Only used by the NotebookRunner businesses."
        ),
        examples=[
            {"some/dir/some_notebook.ipynb"},
            {"dont/run/these/**", "**/dont_run_prefix_*.ipynb"},
        ],
    )

    only_patterns: set[str] = Field(
        set(),
        title="Only patterns",
        description=(
            "Only Notebooks that match ALL of these pattern will be run."
            " Patterns are python pathlib glob patterns:"
            " https://docs.python.org/3/library/pathlib.html#pathlib-pattern-language"
            " Only used by the NotebookRunner businesses."
        ),
        examples=[
            {"run/only/in/these/dirs/**", "**/only_with_this_prefix_*.ipynb"},
        ],
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
