"""Business config type helpers."""

from typing import TypeAlias

from .empty import EmptyLoopConfig
from .gitlfs import GitLFSConfig
from .muster import MusterConfig
from .notebookrunnercounting import NotebookRunnerCountingConfig
from .notebookrunnerinfinite import NotebookRunnerInfiniteConfig
from .notebookrunnerlist import NotebookRunnerListConfig
from .nubladopythonloop import NubladoPythonLoopConfig
from .siaquerysetrunner import SIAQuerySetRunnerConfig
from .tapqueryrunner import TAPQueryRunnerConfig
from .tapquerysetrunner import TAPQuerySetRunnerConfig

__all__ = ["BusinessConfigType"]

BusinessConfigType: TypeAlias = (
    TAPQueryRunnerConfig
    | GitLFSConfig
    | MusterConfig
    | NotebookRunnerCountingConfig
    | NotebookRunnerListConfig
    | NotebookRunnerInfiniteConfig
    | NubladoPythonLoopConfig
    | TAPQuerySetRunnerConfig
    | SIAQuerySetRunnerConfig
    | EmptyLoopConfig
)
"""A union type alias of all of all busines config types."""
