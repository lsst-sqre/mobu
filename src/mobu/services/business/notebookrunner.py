"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Jupyter lab.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

from git.repo import Repo
from structlog.stdlib import BoundLogger

from ...exceptions import NotebookRepositoryError
from ...models.business.notebookrunner import (
    NotebookRunnerData,
    NotebookRunnerOptions,
)
from ...models.user import AuthenticatedUser
from ...storage.jupyter import JupyterLabSession
from .jupyterpythonloop import JupyterPythonLoop

__all__ = ["NotebookRunner"]


class NotebookRunner(JupyterPythonLoop):
    """Start a Jupyter lab and run a sequence of notebooks.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: NotebookRunnerOptions,
        user: AuthenticatedUser,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, logger)
        self.notebook: Optional[Path] = None
        self.running_code: Optional[str] = None
        self._repo_dir = TemporaryDirectory()
        self._repo: Optional[Repo] = None
        self._notebook_paths: Optional[list[Path]] = None

    def annotations(self) -> dict[str, str]:
        result = super().annotations()
        if self.notebook:
            result["notebook"] = self.notebook.name
        return result

    async def startup(self) -> None:
        if not self._repo:
            self.clone_repo()
        self._notebook_paths = self.find_notebooks()
        self.logger.info("Repository cloned and ready")
        await super().startup()

    def clone_repo(self) -> None:
        url = self.options.repo_url
        branch = self.options.repo_branch
        path = self._repo_dir.name
        with self.timings.start("clone_repo"):
            self._repo = Repo.clone_from(url, path, branch=branch)

    def find_notebooks(self) -> list[Path]:
        with self.timings.start("find_notebooks"):
            notebooks = [
                p
                for p in Path(self._repo_dir.name).iterdir()
                if p.suffix == ".ipynb"
            ]
            if not notebooks:
                msg = "No notebooks found in {self._repo_dir.name}"
                raise NotebookRepositoryError(msg)
            random.shuffle(notebooks)
        return notebooks

    def next_notebook(self) -> Path:
        if not self._notebook_paths:
            self.logger.info("Done with this cycle of notebooks")
            self._notebook_paths = self.find_notebooks()
        return self._notebook_paths.pop()

    def read_notebook(self, notebook: Path) -> list[dict[str, Any]]:
        with self.timings.start("read_notebook", {"notebook": notebook.name}):
            try:
                notebook_text = notebook.read_text()
                cells = json.loads(notebook_text)["cells"]
            except Exception as e:
                msg = f"Invalid notebook {notebook.name}: {str(e)}"
                raise NotebookRepositoryError(msg)

        # Add cell numbers to all the cells, which we'll use to name timing
        # events so that we can find cells that take an excessively long time
        # to run.
        #
        # We will prefer to use the id attribute of the cell if present, but
        # some of our notebooks are in the older format without an id.
        for i, cell in enumerate(cells, start=1):
            cell["_index"] = str(i)

        # Strip non-code cells.
        cells = [c for c in cells if c["cell_type"] == "code"]

        return cells

    async def create_session(
        self, notebook_name: Optional[str] = None
    ) -> JupyterLabSession:
        """Override create_session to add the notebook name."""
        if not notebook_name:
            notebook_name = self.notebook.name if self.notebook else None
        return await super().create_session(notebook_name)

    async def execute_code(self, session: JupyterLabSession) -> None:
        for count in range(self.options.max_executions):
            self.notebook = self.next_notebook()

            iteration = f"{count + 1}/{self.options.max_executions}"
            msg = f"Notebook {self.notebook.name} iteration {iteration}"
            self.logger.info(msg)

            for cell in self.read_notebook(self.notebook):
                code = "".join(cell["source"])
                if "id" in cell:
                    cell_id = f'`{cell["id"]}` (#{cell["_index"]})'
                else:
                    cell_id = f'#{cell["_index"]}'
                await self.execute_cell(session, code, cell_id)
                if not await self.execution_idle():
                    break

            self.logger.info(f"Success running notebook {self.notebook.name}")
            if self.stopping:
                break

    async def execute_cell(
        self, session: JupyterLabSession, code: str, cell_id: str
    ) -> None:
        assert self.notebook
        self.logger.info(f"Executing cell {cell_id}:\n{code}\n")
        annotations = self.annotations()
        annotations["cell"] = cell_id
        with self.timings.start("execute_cell", annotations):
            self.running_code = code
            reply = await self._client.run_python(session, code)
            self.running_code = None
        self.logger.info(f"Result:\n{reply}\n")

    def dump(self) -> NotebookRunnerData:
        return NotebookRunnerData(
            notebook=self.notebook.name if self.notebook else None,
            running_code=self.running_code,
            **super().dump().dict(),
        )