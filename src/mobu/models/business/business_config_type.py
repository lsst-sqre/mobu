"""Business config type helpers."""

from typing import TypeAlias

from .empty import EmptyLoopConfig
from .gitlfs import GitLFSConfig
from .notebookrunner import NotebookRunnerConfig
from .nubladopythonloop import NubladoPythonLoopConfig
from .siaquerysetrunner import SIAQuerySetRunnerConfig
from .tapqueryrunner import TAPQueryRunnerConfig
from .tapquerysetrunner import TAPQuerySetRunnerConfig

BusinessConfigType: TypeAlias = (
    TAPQueryRunnerConfig
    | GitLFSConfig
    | NotebookRunnerConfig
    | NubladoPythonLoopConfig
    | TAPQuerySetRunnerConfig
    | SIAQuerySetRunnerConfig
    | EmptyLoopConfig
)
"""A union type alias of all of all busines config types."""
