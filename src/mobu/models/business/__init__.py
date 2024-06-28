from typing import TypeAlias

from ...models.business.empty import EmptyLoopConfig
from ...models.business.gitlfs import GitLFSConfig
from ...models.business.notebookrunner import NotebookRunnerConfig
from ...models.business.nubladopythonloop import NubladoPythonLoopConfig
from ...models.business.tapqueryrunner import TAPQueryRunnerConfig
from ...models.business.tapquerysetrunner import TAPQuerySetRunnerConfig

BusinessConfigType: TypeAlias = (
    TAPQueryRunnerConfig
    | GitLFSConfig
    | NotebookRunnerConfig
    | NubladoPythonLoopConfig
    | TAPQuerySetRunnerConfig
    | EmptyLoopConfig
)
