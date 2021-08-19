"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Jupyter lab.
"""

from __future__ import annotations

import json
from pathlib import Path
from random import SystemRandom
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import git

from ..exceptions import NotebookRepositoryError
from ..jupyterclient import JupyterLabSession
from ..models.business import BusinessData
from .jupyterpythonloop import JupyterPythonLoop

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional

    from structlog import BoundLogger

    from ..models.business import BusinessConfig
    from ..models.user import AuthenticatedUser

__all__ = ["NotebookRunner"]


class NotebookRunner(JupyterPythonLoop):
    """Start a Jupyter lab and run a sequence of notebooks."""

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        self.notebook: Optional[Path] = None
        self.running_code: Optional[str] = None
        self._repo_dir = TemporaryDirectory()
        self._repo: Optional[git.Repo] = None
        self._notebook_paths: Optional[List[Path]] = None

    async def startup(self) -> None:
        if not self._repo:
            self.clone_repo()
        self._notebook_paths = self.find_notebooks()
        self.logger.info("Repository cloned and ready")
        await super().startup()

    def clone_repo(self) -> None:
        url = self.config.repo_url
        branch = self.config.repo_branch
        path = self._repo_dir.name
        with self.timings.start("clone_repo"):
            self._repo = git.Repo.clone_from(url, path, branch=branch)

    def find_notebooks(self) -> List[Path]:
        with self.timings.start("find_notebooks"):
            notebooks = [
                p
                for p in Path(self._repo_dir.name).iterdir()
                if p.suffix == ".ipynb"
            ]
            if not notebooks:
                msg = "No notebooks found in {self._repo_dir.name}"
                raise NotebookRepositoryError(msg)
            SystemRandom().shuffle(notebooks)
        return notebooks

    def next_notebook(self) -> None:
        if not self._notebook_paths:
            self.logger.info("Done with this cycle of notebooks")
            self._notebook_paths = self.find_notebooks()
        self.notebook = self._notebook_paths.pop()

    def read_notebook(self, notebook: Path) -> List[Dict[str, Any]]:
        with self.timings.start("read_notebook", {"notebook": notebook.name}):
            try:
                notebook_text = notebook.read_text()
                cells = json.loads(notebook_text)["cells"]
            except Exception as e:
                msg = f"Invalid notebook {notebook.name}: {str(e)}"
                raise NotebookRepositoryError(msg)

        # Add cell numbers to all the cells, which we'll use to name timing
        # events so that we can find cells that take an excessively long time
        # to run.  Do this before we strip all non-code cells so that we can
        # correlate to the original notebook.
        #
        # We will prefer to use the id attribute of the cell if present, but
        # some of our notebooks are in the older format without an id.
        for i, cell in enumerate(cells, start=1):
            cell["_index"] = str(i)

        return [c for c in cells if c["cell_type"] == "code"]

    async def create_session(
        self, notebook_name: Optional[str] = None
    ) -> JupyterLabSession:
        """Override create_session to add the notebook name."""
        if not notebook_name:
            notebook_name = self.notebook.name if self.notebook else None
        return await super().create_session(notebook_name)

    async def execute_code(self, session: JupyterLabSession) -> None:
        for count in range(self.config.max_executions):
            self.next_notebook()
            assert self.notebook

            iteration = f"{count + 1}/{self.config.max_executions}"
            msg = f"Notebook {self.notebook.name} iteration {iteration}"
            self.logger.info(msg)

            for cell in self.read_notebook(self.notebook):
                code = "".join(cell["source"])
                if "id" in cell:
                    cell_id = f'`{cell["id"]}` (#{cell["_index"]})'
                else:
                    cell_id = f'#{cell["_index"]}'
                await self.execute_cell(session, code, cell_id)
                await self.execution_idle()
                if self.stopping:
                    break

            if self.stopping:
                break
            self.logger.info(f"Success running notebook {self.notebook.name}")

    async def execute_cell(
        self, session: JupyterLabSession, code: str, cell_id: str
    ) -> None:
        assert self.notebook
        self.logger.info("Executing:\n%s\n", code)
        annotations = {"notebook": self.notebook.name, "cell": cell_id}
        if self.node:
            annotations["node"] = self.node
        with self.timings.start("execute_cell", annotations):
            self.running_code = code
            reply = await self._client.run_python(session, code)
            self.running_code = None
        self.logger.info(f"Result:\n{reply}\n")

    def dump(self) -> BusinessData:
        data = super().dump()
        data.running_code = self.running_code
        data.notebook = self.notebook.name if self.notebook else None
        return data
