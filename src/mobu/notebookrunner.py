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

from mobu.jupyterclient import JupyterClient, NotebookException
from mobu.jupyterloginloop import JupyterLoginLoop
from mobu.timing import CodeTimingData, NotebookTimingData, TimeInfo

REPO_URL = "https://github.com/lsst-sqre/notebook-demo.git"
REPO_BRANCH = "prod"


@dataclass
class NotebookRunner(JupyterLoginLoop):
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
            startstamp = NotebookTimingData(start=TimeInfo.stamp())
            self.timings.append(startstamp)
            if not self._repo:
                repo_url = self.options.get("repo_url", REPO_URL)
                repo_branch = self.options.get("repo_branch", REPO_BRANCH)

                self._repo = git.Repo.clone_from(
                    repo_url, self._repo_dir.name, branch=repo_branch
                )
                startstamp.repo_cloned = TimeInfo.stamp(
                    previous=startstamp.start
                )

            self._notebook_iterator = os.scandir(self._repo_dir.name)

            logger.info("Repository cloned and ready")

            prev = startstamp.repo_cloned
            if not prev:
                prev = startstamp.start

            await self._client.hub_login()
            startstamp.login_complete = TimeInfo.stamp(previous=prev)

            await self._client.delete_lab()
            startstamp.lab_deleted = TimeInfo.stamp(startstamp.login_complete)

            while True:
                self._next_notebook()

                await self._client.ensure_lab()
                await asyncio.sleep(self.options.get("settle_time", 0))

                # Start timer after settle
                stamp = NotebookTimingData(start=TimeInfo.stamp())
                self.timings.append(stamp)
                if self.notebook.path.endswith(".ipynb"):
                    logger.info(f"Starting notebook: {self.notebook.name}")
                    notebook_text = Path(self.notebook.path).read_text()
                    cells = json.loads(notebook_text)["cells"]

                    kernel = await self._client.create_kernel(
                        kernel_name="LSST"
                    )
                    stamp.kernel_created = TimeInfo.stamp(previous=stamp.start)

                    for cell in cells:
                        if cell["cell_type"] == "code":
                            self.code = "".join(cell["source"])
                            runstamp = CodeTimingData(start=TimeInfo.stamp())
                            runstamp.code = self.code
                            stamp.code.append(runstamp)
                            logger.info("Executing:\n%s\n", self.code)
                            reply = await self._client.run_python(
                                kernel, self.code
                            )
                            runstamp.stop = TimeInfo.stamp(
                                previous=runstamp.start
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

    async def stop(self) -> None:
        await self._client.delete_lab()

    def dump(self) -> dict:
        r = super().dump()
        r.update(
            {
                "name": "NotebookRunner",
                "running_code": self.code,
            }
        )
        n = None
        if hasattr(self, "notebook") and self.notebook:
            n = self.notebook.name
        r.update({"notebook": n})
        return r

    def _next_notebook(self) -> None:
        try:
            self.notebook = next(self._notebook_iterator)
        except StopIteration:
            self.monkey.log.info(
                "Done with this cycle of notebooks, recreating lab."
            )
            self._notebook_iterator = os.scandir(self._repo_dir.name)
            self._next_notebook()
