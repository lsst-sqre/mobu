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

from mobu.business.jupyterloginloop import JupyterLoginLoop
from mobu.jupyterclient import NotebookException

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

    async def run(self) -> None:
        try:
            nb_iterations = self.options.get("notebook_iterations", 1)
            if not self._repo:
                repo_url = self.options.get("repo_url", REPO_URL)
                repo_branch = self.options.get("repo_branch", REPO_BRANCH)
                self.start_event("clone_repo")
                self._repo = git.Repo.clone_from(
                    repo_url, self._repo_dir.name, branch=repo_branch
                )
                self.stop_current_event()

            self._notebook_iterator = os.scandir(self._repo_dir.name)

            self.logger.info("Repository cloned and ready")

            self.start_event("hub_login")
            await self._client.hub_login()
            self.stop_current_event()
            self._last_login = self._now()
            self.start_event("initial_delete_lab")
            await self._client.delete_lab()
            self.stop_current_event()

            while True:
                self._next_notebook()
                assert self.notebook
                self.start_event("ensure_lab")
                await self._client.ensure_lab()
                self.stop_current_event()
                self.start_event("lab_settle")
                await asyncio.sleep(self.options.get("settle_time", 0))
                self.stop_current_event()
                if self.notebook.path.endswith(".ipynb"):
                    self.logger.info(
                        f"Starting notebook: {self.notebook.name}"
                    )
                    self.start_event(f"read_notebook:{self.notebook.name}")
                    notebook_text = Path(self.notebook.path).read_text()
                    cells = json.loads(notebook_text)["cells"]
                    self.stop_current_event()
                    self.start_event("create_kernel")
                    kernel = await self._client.create_kernel(
                        kernel_name="LSST"
                    )
                    self.stop_current_event()
                    for count in range(nb_iterations):
                        self.logger.info(
                            f"Notebook '{self.notebook.name}'"
                            + f" iteration {count + 1}"
                            + f"/{nb_iterations}"
                        )
                        await self._reauth_if_needed()
                        for cell in cells:
                            if cell["cell_type"] == "code":
                                self.code = "".join(cell["source"])
                                self.logger.info("Executing:\n%s\n", self.code)
                                self.start_event("run_code")
                                sw = self.get_current_event()
                                reply = await self._client.run_python(
                                    kernel, self.code
                                )
                                if sw is not None:
                                    sw.annotation = {
                                        "code": self.code,
                                        "result": reply,
                                    }
                                self.stop_current_event()
                                self.logger.info(f"Result:\n{reply}\n")
                    self.logger.info(f"Deleting kernel {kernel}")
                    self.start_event("delete_kernel")
                    await self._client.delete_kernel(kernel)
                    self.stop_current_event()
                    self.logger.info(
                        f"Success running notebook: {self.notebook.name}"
                    )

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

    def dump(self) -> dict:
        r = super().dump()
        r.update({"running_code": self.code})
        n = None
        if self.notebook:
            n = self.notebook.name
        r.update({"notebook": n})
        return r

    def _next_notebook(self) -> None:
        assert self._notebook_iterator
        try:
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
            self.logger.info("Reauthenticating to Hub")
            self.start_event("hub_reauth")
            await self._client.hub_login()
            self.stop_current_event()
            self._last_login = now
