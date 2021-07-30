"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Jupyter lab.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import git

from ..jupyterclient import JupyterLabSession, NotebookException
from ..models.business import BusinessData
from .jupyterpythonloop import JupyterPythonLoop

if TYPE_CHECKING:
    from typing import Any, Dict, Iterator, List, Optional

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
        self.notebook: Optional[os.DirEntry] = None
        self.running_code: Optional[str] = None
        self._failed_notebooks: List[str] = []
        self._repo_dir = TemporaryDirectory()
        self._repo: Optional[git.Repo] = None
        self._notebook_iterator: Optional[Iterator[os.DirEntry]] = None

    async def startup(self) -> None:
        if not self._repo:
            self.clone_repo()
        self._notebook_iterator = os.scandir(self._repo_dir.name)
        self.logger.info("Repository cloned and ready")
        await super().startup()

    def clone_repo(self) -> None:
        url = self.config.repo_url
        branch = self.config.repo_branch
        path = self._repo_dir.name
        with self.timings.start("clone_repo"):
            self._repo = git.Repo.clone_from(url, path, branch=branch)

    async def execute_code(self, session: JupyterLabSession) -> None:
        for count in range(self.config.max_executions):
            self._next_notebook()
            assert self.notebook
            self.logger.info(f"Starting notebook: {self.notebook.name}")
            cells = self.read_notebook(self.notebook.name, self.notebook.path)

            iteration = f"{count + 1}/{self.config.max_executions}"
            msg = f"Notebook '{self.notebook.name}' iteration {iteration}"
            self.logger.info(msg)

            for cell in cells:
                self.running_code = "".join(cell["source"])
                await self.execute_cell(session, self.running_code)
                self.running_code = None
                await self.execution_idle()
                if self.stopping:
                    break

            if self.stopping:
                break
            self.logger.info(f"Success running notebook: {self.notebook.name}")

    def read_notebook(self, name: str, path: str) -> List[Dict[str, Any]]:
        with self.timings.start(f"read_notebook:{name}"):
            notebook_text = Path(path).read_text()
            cells = json.loads(notebook_text)["cells"]
        return [c for c in cells if c["cell_type"] == "code"]

    async def create_session(self) -> JupyterLabSession:
        """Override create_session to add the notebook name."""
        self.logger.info("Creating lab session")
        notebook_name = self.notebook.name if self.notebook else None
        with self.timings.start("create_session"):
            session = await self._client.create_labsession(
                notebook_name=notebook_name
            )
        return session

    async def execute_cell(
        self, session: JupyterLabSession, code: str
    ) -> None:
        self.logger.info("Executing:\n%s\n", code)
        try:
            with self.timings.start("run_code", {"code": code}) as sw:
                reply = await self._client.run_python(session, code)
                sw.annotation["result"] = reply
            self.logger.info(f"Result:\n{reply}\n")
        except NotebookException as e:
            running_code = self.running_code
            notebook_name = "no notebook"
            if self.notebook:
                self._failed_notebooks.append(self.notebook.name)
                notebook_name = self.notebook.name
            self.logger.error(f"Error running notebook: {notebook_name}")
            self.running_code = None
            raise NotebookException(
                f"Running {notebook_name}: '"
                f"```{running_code}``` generated: ```{e}```"
            )

    def dump(self) -> BusinessData:
        data = super().dump()
        data.running_code = self.running_code
        data.notebook = self.notebook.name if self.notebook else None
        return data

    def _next_notebook(self) -> None:
        assert self._notebook_iterator
        try:
            self.notebook = next(self._notebook_iterator)
            while not self.notebook.path.endswith(".ipynb"):
                self.notebook = next(self._notebook_iterator)
        except StopIteration:
            self.logger.info("Done with this cycle of notebooks")
            self._notebook_iterator = os.scandir(self._repo_dir.name)
            self._next_notebook()
