"""Business config type helpers."""

from typing import TypeAlias

from .empty import EmptyLoopConfig
from .gitlfs import GitLFSConfig
from .notebookrunnercounting import NotebookRunnerCountingConfig
from .notebookrunnerlist import NotebookRunnerListConfig
from .nubladopythonloop import NubladoPythonLoopConfig
from .siaquerysetrunner import SIAQuerySetRunnerConfig
from .tapqueryrunner import TAPQueryRunnerConfig
from .tapquerysetrunner import TAPQuerySetRunnerConfig

BusinessConfigType: TypeAlias = (
    TAPQueryRunnerConfig
    | GitLFSConfig
    | NotebookRunnerCountingConfig
    | NotebookRunnerListConfig
    | NubladoPythonLoopConfig
    | TAPQuerySetRunnerConfig
    | SIAQuerySetRunnerConfig
    | EmptyLoopConfig
)
"""A union type alias of all of all busines config types."""
