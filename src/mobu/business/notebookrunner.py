"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, randomly pick
the notebooks, and run them on the remote Jupyter lab.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import git

from ..jupyterclient import NotebookException
from .jupyterloginloop import JupyterLoginLoop

if TYPE_CHECKING:
    from typing import Any, Dict, Iterator, List, Optional

    from structlog import BoundLogger

    from ..user import User

__all__ = ["NotebookRunner"]

REPO_URL = "https://github.com/lsst-sqre/notebook-demo.git"
REPO_BRANCH = "prod"


class NotebookRunner(JupyterLoginLoop):
    """Start a Jupyter lab and run a sequence of notebooks."""

    def __init__(
        self, logger: BoundLogger, options: Dict[str, Any], user: User
    ) -> None:
        super().__init__(logger, options, user)
        self._failed_notebooks: List[str] = []
        self._last_login = datetime.fromtimestamp(0, tz=timezone.utc)
        self._repo_dir = TemporaryDirectory()
        self._repo: Optional[git.Repo] = None
        self._notebook_iterator: Optional[Iterator[os.DirEntry]] = None
        self.notebook: Optional[os.DirEntry] = None
        self.code = ""

    async def setup(self) -> None:
        if not self._repo:
            self.clone_repo()
        self._notebook_iterator = os.scandir(self._repo_dir.name)
        self.logger.info("Repository cloned and ready")
        await super().startup()
        self._last_login = self._now()
        await self.initial_delete_lab()

    def clone_repo(self) -> None:
        url = self.options.get("repo_url", REPO_URL)
        branch = self.options.get("repo_branch", REPO_BRANCH)
        path = self._repo_dir.name
        with self.timings.start("clone_repo"):
            self._repo = git.Repo.clone_from(url, path, branch=branch)

    async def initial_delete_lab(self) -> None:
        with self.timings.start("initial_delete_lab"):
            await self._client.delete_lab()

    async def lab_business(self) -> None:
        self._next_notebook()
        assert self.notebook

        await self.ensure_lab()
        await self.lab_settle()
        kernel = await self.create_kernel()

        self.logger.info(f"Starting notebook: {self.notebook.name}")
        cells = self.read_notebook(self.notebook.name, self.notebook.path)
        nb_iterations = self.options.get("notebook_iterations", 1)
        for count in range(nb_iterations):
            iteration = f"{count + 1}/{nb_iterations}"
            msg = f"Notebook '{self.notebook.name}' iteration {iteration}"
            self.logger.info(msg)

            await self._reauth_if_needed()

            for cell in cells:
                self.code = "".join(cell["source"])
                await self.execute_code(kernel, self.code)

        await self.delete_kernel(kernel)
        self.logger.info(f"Success running notebook: {self.notebook.name}")

    async def lab_settle(self) -> None:
        with self.timings.start("lab_settle"):
            await asyncio.sleep(self.options.get("settle_time", 0))

    def read_notebook(self, name: str, path: str) -> List[Dict[str, Any]]:
        with self.timings.start(f"read_notebook:{name}"):
            notebook_text = Path(path).read_text()
            cells = json.loads(notebook_text)["cells"]
        return [c for c in cells if c["cell_type"] == "code"]

    async def create_kernel(self) -> str:
        self.logger.info("create_kernel")
        with self.timings.start("create_kernel"):
            kernel = await self._client.create_kernel()
        return kernel

    async def execute_code(self, kernel: str, code: str) -> None:
        self.logger.info("Executing:\n%s\n", code)
        with self.timings.start("run_code", {"code": code}) as sw:
            reply = await self._client.run_python(kernel, code)
            sw.annotation["result"] = reply
        self.logger.info(f"Result:\n{reply}\n")

    async def delete_kernel(self, kernel: str) -> None:
        self.logger.info(f"Deleting kernel {kernel}")
        with self.timings.start("delete_kernel"):
            await self._client.delete_kernel(kernel)

    async def run(self) -> None:
        self.logger.info("Starting up...")
        await self.startup()
        while True:
            self.logger.info("Starting next iteration")
            try:
                await self.lab_business()
                self.success_count += 1
            except NotebookException as e:
                notebook_name = "no notebook"
                if self.notebook:
                    self._failed_notebooks.append(self.notebook.name)
                    notebook_name = self.notebook.name
                self.logger.error(f"Error running notebook: {notebook_name}")
                self.failure_count += 1
                raise NotebookException(
                    f"Running {notebook_name}: '"
                    f"```{self.code}``` generated: ```{e}```"
                )
            except Exception:
                self.failure_count += 1
                raise

    def dump(self) -> dict:
        r = super().dump()
        r["running_code"] = self.code
        r["notebook"] = self.notebook.name if self.notebook else None
        return r

    def _next_notebook(self) -> None:
        assert self._notebook_iterator
        try:
            self.notebook = next(self._notebook_iterator)
            while not self.notebook.path.endswith(".ipynb"):
                self.notebook = next(self._notebook_iterator)
        except StopIteration:
            self.logger.info(
                "Done with this cycle of notebooks, recreating lab."
            )
            self._notebook_iterator = os.scandir(self._repo_dir.name)
            self._next_notebook()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def _reauth_if_needed(self) -> None:
        now = self._now()
        elapsed = now - self._last_login
        if elapsed > timedelta(minutes=45):
            await self.hub_reauth()
            self._last_login = now

    async def hub_reauth(self) -> None:
        self.logger.info("Reauthenticating to Hub")
        with self.timings.start("hub_reauth"):
            await self._client.hub_login()
