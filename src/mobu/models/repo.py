"""Models related to GitHub repos for the GitHub CI app functionality."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ClonedRepoInfo", "RepoConfig"]


class RepoConfig(BaseModel):
    """In-repo configuration for mobu behavior.

    This can be placed into a yaml file in the root of a repo to configure
    certain mobu behavior.
    """

    model_config = ConfigDict(extra="forbid")

    exclude_dirs: set[Path] = Field(
        set(),
        title="Any notebooks in these directories will not be run",
        description=(
            " These directories are relative to the repo root. Any notebooks"
            " in child directories of these directories will also be excluded."
        ),
        examples=["some-dir", "some-dir/some-other-dir"],
    )


@dataclass(frozen=True)
class ClonedRepoInfo:
    """Information about a cloned git repo."""

    dir: TemporaryDirectory
    path: Path
    hash: str
