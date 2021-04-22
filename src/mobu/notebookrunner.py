"""NotebookRunner logic for mobu.

This business pattern will clone a git repo full
of notebooks, randomly pick the notebooks, and run
them on the remote jupyter lab."""

__all__ = [
    "NotebookRunner",
]

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import git

from mobu.business import Business
from mobu.jupyterclient import JupyterClient, NotebookException

REPO_URL = "https://github.com/lsst-sqre/notebook-demo.git"
REPO_BRANCH = "prod"


@dataclass
class NotebookRunner(Business):
    success_count: int = 0
    failure_count: int = 0
    _client: JupyterClient = field(init=False)
    _failed_notebooks: list = field(init=False, default_factory=list)
    _repo_dir: TemporaryDirectory = field(
        init=False, default_factory=TemporaryDirectory
    )
    _repo: git.Repo = field(init=False, default=None)
    _notebook_iterator: Iterator = field(init=False)
    notebook: os.DirEntry = field(init=False)
    code: str = field(init=False, default="")

    async def run(self) -> None:
        try:
            logger = self.monkey.log

            self._client = JupyterClient(
                self.monkey.user, logger, self.options
            )

            if not self._repo:
                repo_url = self.options.get("repo_url", REPO_URL)
                repo_branch = self.options.get("repo_branch", REPO_BRANCH)

                self._repo = git.Repo.clone_from(
                    repo_url, self._repo_dir.name, branch=repo_branch
                )

            self._notebook_iterator = os.scandir(self._repo_dir.name)

            logger.info("Repository cloned and ready")

            await self._client.hub_login()

            while True:
                self._next_notebook()

                if self.success_count % 100 == 0:
                    await self._client.delete_lab()

                await self._client.ensure_lab()

                await asyncio.sleep(self.options.get("settle_time", 0))

                if self.notebook.path.endswith(".ipynb"):
                    logger.info(f"Starting notebook: {self.notebook.name}")
                    notebook_text = Path(self.notebook.path).read_text()
                    cells = json.loads(notebook_text)["cells"]

                    kernel = await self._client.create_kernel(
                        kernel_name="LSST"
                    )

                    for cell in cells:
                        if cell["cell_type"] == "code":
                            self.code = "".join(cell["source"])
                            logger.info("Executing:\n%s\n", self.code)
                            reply = await self._client.run_python(
                                kernel, self.code
                            )

                            if reply:
                                logger.info(f"Response:\n{reply}\n")

                    logger.info(
                        f"Success running notebook: {self.notebook.name}"
                    )

                    self.success_count += 1

        except NotebookException as e:
            logger.error(f"Error running notebook: {self.notebook.name}")
            self._failed_notebooks.append(self.notebook.name)
            self.failure_count += 1
            raise NotebookException(
                f"Running {self.notebook.name}: '"
                f"```{self.code}``` generated: ```{e}```"
            )

    def dump(self) -> dict:
        return {
            "name": "NotebookRunner",
            "current_notebook": self.notebook.name,
            "running_code": self.code,
            "failed_notebooks": self._failed_notebooks,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "jupyter_client": self._client.dump(),
        }

    def _next_notebook(self) -> None:
        try:
            self.notebook = next(self._notebook_iterator)
        except StopIteration:
            self.monkey.log.info(
                "Done with this cycle of notebooks, recreating lab."
            )
            self._notebook_iterator = os.scandir(self._repo_dir.name)
            self._next_notebook()
