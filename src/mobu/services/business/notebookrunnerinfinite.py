"""Execute all notebooks in a single JupyterLab session."""

import itertools
from typing import override

from .notebookrunner import ExecutionIteration, NotebookRunner

__all__ = ["NotebookRunnerInfinite"]


class NotebookRunnerInfinite(NotebookRunner):
    """A notebook runner that never refreshes JupyterLab sessions or deletes
    labs until mobu is shut down.
    """

    @override
    def execution_iterator(self) -> ExecutionIteration:
        return ExecutionIteration(iterator=itertools.count(), size="infinite")
