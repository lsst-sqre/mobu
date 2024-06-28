"""Models related to GitHub repos for the GitHub CI app functionality."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RepoConfig(BaseModel):
    """In-repo configuration for mobu behavior.

    This can be placed into a yaml file in the root of a repo to configure
    certain mobu behavior.
    """

    exclude_dirs: set[Path] = Field(
        set(),
        title="Any notebooks in these directories will not be run",
        description=(
            " These directories are relative to the repo root. Any notebooks"
            " in child directories of these directories will also be excluded."
        ),
        examples=["some-dir", "some-dir/some-other-dir"],
    )

    model_config = ConfigDict(extra="forbid")
