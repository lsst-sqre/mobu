"""Models related to GitHub repos for the GitHub CI app functionality."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ConfigDict

from .business.notebookrunner import Filterable

__all__ = ["ClonedRepoInfo", "RepoConfig"]


class RepoConfig(Filterable):
    """In-repo configuration for mobu behavior.

    This can be placed into a yaml file in the root of a repo to configure
    certain mobu behavior.
    """

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ClonedRepoInfo:
    """Information about a cloned git repo."""

    dir: TemporaryDirectory
    path: Path
    hash: str
