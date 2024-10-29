"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Nublado lab.
"""

from __future__ import annotations

import json
import random
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from httpx import AsyncClient
from rubin.nublado.client import JupyterLabSession
from rubin.nublado.client.models import CodeContext
from structlog.stdlib import BoundLogger

from ...config import config
from ...constants import GITHUB_REPO_CONFIG_PATH
from ...exceptions import NotebookRepositoryError, RepositoryConfigError
from ...models.business.notebookrunner import (
    ListNotebookRunnerOptions,
    NotebookFilterResults,
    NotebookMetadata,
    NotebookRunnerData,
    NotebookRunnerOptions,
)
from ...models.repo import RepoConfig
from ...models.user import AuthenticatedUser
from ...storage.git import Git
from .nublado import NubladoBusiness

__all__ = ["NotebookRunner"]


class NotebookRunner(NubladoBusiness):
    """Start a Jupyter lab and run a sequence of notebooks.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    http_client
        Shared HTTP client for general web access.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: NotebookRunnerOptions | ListNotebookRunnerOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._notebook: Path | None = None
        self._notebook_paths: list[Path] | None = None
        self._repo_dir: Path | None = None
        self._exclude_paths: set[Path] = set()
        self._running_code: str | None = None
        self._git = Git(logger=logger)
        self._max_executions: int | None = None
        self._notebooks_to_run: list[Path] | None = None

        match options:
            case NotebookRunnerOptions(max_executions=max_executions):
                self._max_executions = max_executions
            case ListNotebookRunnerOptions(notebooks_to_run=notebooks_to_run):
                self._notebooks_to_run = notebooks_to_run

    def annotations(self, cell_id: str | None = None) -> dict[str, str]:
        result = super().annotations()
        if self._notebook:
            result["notebook"] = self._notebook.name
        if cell_id:
            result["cell"] = cell_id
        return result

    async def startup(self) -> None:
        await self.initialize()
        await super().startup()

    async def cleanup(self) -> None:
        shutil.rmtree(str(self._repo_dir))
        self._repo_dir = None
        self._notebook_filter_results = None

    async def initialize(self) -> None:
        """Prepare to run the business.

        * Check out the repository
        * Parse the in-repo config
        * Filter the notebooks
        """
        if self._repo_dir is None:
            self._repo_dir = Path(TemporaryDirectory(delete=False).name)
            await self.clone_repo()

        repo_config_path = self._repo_dir / GITHUB_REPO_CONFIG_PATH
        if repo_config_path.exists():
            try:
                repo_config = RepoConfig.model_validate(
                    yaml.safe_load(repo_config_path.read_text())
                )
            except Exception as err:
                raise RepositoryConfigError(
                    err=err,
                    user=self.user.username,
                    config_file=GITHUB_REPO_CONFIG_PATH,
                    repo_url=self.options.repo_url,
                    repo_ref=self.options.repo_ref,
                ) from err
        else:
            repo_config = RepoConfig()

        exclude_dirs = repo_config.exclude_dirs
        self._exclude_paths = {self._repo_dir / path for path in exclude_dirs}
        self._notebooks = self.find_notebooks()
        self.logger.info("Repository cloned and ready")

    async def shutdown(self) -> None:
        await self.cleanup()
        await super().shutdown()

    async def refresh(self) -> None:
        self.logger.info("Recloning notebooks and forcing new execution")
        await self.cleanup()
        await self.initialize()
        self.refreshing = False

    async def clone_repo(self) -> None:
        url = self.options.repo_url
        ref = self.options.repo_ref
        with self.timings.start("clone_repo"):
            self._git.repo = self._repo_dir
            await self._git.clone(url, str(self._repo_dir))
            await self._git.checkout(ref)

    def is_excluded(self, notebook: Path) -> bool:
        # A notebook is excluded if any of its parent directories are excluded
        return bool(set(notebook.parents) & self._exclude_paths)

    def missing_services(self, notebook: Path) -> bool:
        """Return True if a notebook declares required services and they are
        available.
        """
        metadata = self.read_notebook_metadata(notebook)
        missing_services = (
            metadata.required_services - config.available_services
        )
        if missing_services:
            msg = "Environment does not provide required services for notebook"
            self.logger.info(
                msg,
                notebook=notebook,
                required_services=metadata.required_services,
                missing_services=missing_services,
            )
            return True
        return False

    def find_notebooks(self) -> NotebookFilterResults:
        with self.timings.start("find_notebooks"):
            if self._repo_dir is None:
                raise NotebookRepositoryError(
                    "Repository directory must be set", self.user.username
                )

            all_notebooks = set(self._repo_dir.glob("**/*.ipynb"))
            if not all_notebooks:
                msg = "No notebooks found in {self._repo_dir}"
                raise NotebookRepositoryError(msg, self.user.username)

            filter_results = NotebookFilterResults(all=all_notebooks)
            filter_results.excluded_by_dir = {
                n for n in filter_results.all if self.is_excluded(n)
            }
            filter_results.excluded_by_service = {
                n for n in filter_results.all if self.missing_services(n)
            }

            if self._notebooks_to_run:
                requested = {
                    self._repo_dir / notebook
                    for notebook in self._notebooks_to_run
                }
                not_found = requested - filter_results.all
                if not_found:
                    msg = (
                        "Requested notebooks do not exist in"
                        f" {self._repo_dir}: {not_found}"
                    )
                    raise NotebookRepositoryError(msg, self.user.username)
                filter_results.excluded_by_requested = (
                    filter_results.all - requested
                )

            filter_results.runnable = (
                filter_results.all
                - filter_results.excluded_by_service
                - filter_results.excluded_by_dir
                - filter_results.excluded_by_requested
            )
            if bool(filter_results.runnable):
                self.logger.info(
                    "Found notebooks to run",
                    filter_results=filter_results.model_dump(),
                )
            else:
                self.logger.warning(
                    "No notebooks to run after filtering!",
                    filter_results=filter_results.model_dump(),
                )

        return filter_results

    def next_notebook(self) -> Path:
        if not self._notebooks:
            self._notebooks = self.find_notebooks()
        if not self._notebook_paths:
            self._notebook_paths = list(self._notebooks.runnable)
            random.shuffle(self._notebook_paths)
        return self._notebook_paths.pop()

    def read_notebook_metadata(self, notebook: Path) -> NotebookMetadata:
        """Extract mobu-specific metadata from a notebook."""
        with self.timings.start(
            "read_notebook_metadata", {"notebook": notebook.name}
        ):
            try:
                notebook_text = notebook.read_text()
                notebook_json = json.loads(notebook_text)
                metadata = notebook_json["metadata"].get("mobu", {})
                return NotebookMetadata.model_validate(metadata)
            except Exception as e:
                msg = f"Invalid notebook metadata {notebook.name}: {e!s}"
                raise NotebookRepositoryError(msg, self.user.username) from e

    def read_notebook(self, notebook: Path) -> list[dict[str, Any]]:
        with self.timings.start("read_notebook", {"notebook": notebook.name}):
            try:
                notebook_text = notebook.read_text()
                cells = json.loads(notebook_text)["cells"]
            except Exception as e:
                msg = f"Invalid notebook {notebook.name}: {e!s}"
                raise NotebookRepositoryError(msg, self.user.username) from e

        # Strip non-code cells.
        cells = [c for c in cells if c["cell_type"] == "code"]

        # Add cell numbers to all the cells, which we'll use in exception
        # reporting and to annotate timing events so that we can find cells
        # that take an excessively long time to run. This should be done after
        # stripping non-code cells, since the UI for notebooks displays cell
        # numbers only counting code cells.
        for i, cell in enumerate(cells, start=1):
            cell["_index"] = str(i)

        return cells

    @asynccontextmanager
    async def open_session(
        self, notebook_name: str | None = None
    ) -> AsyncIterator[JupyterLabSession]:
        """Override to add the notebook name."""
        if not notebook_name:
            notebook_name = self._notebook.name if self._notebook else None
        async with super().open_session(notebook_name) as session:
            yield session

    async def execute_code(self, session: JupyterLabSession) -> None:
        """Run a set number of notebooks (flocks), or all available (CI)."""
        if self._max_executions:
            num_executions = self._max_executions
        else:
            num_executions = len(self._notebooks.runnable)
        for count in range(num_executions):
            if self.refreshing:
                await self.refresh()
                return

            self._notebook = self.next_notebook()

            iteration = f"{count + 1}/{num_executions}"
            msg = f"Notebook {self._notebook.name} iteration {iteration}"
            self.logger.info(msg)

            for cell in self.read_notebook(self._notebook):
                code = "".join(cell["source"])
                if "id" in cell:
                    cell_id = f'`{cell["id"]}` (#{cell["_index"]})'
                else:
                    cell_id = f'#{cell["_index"]}'
                ctx = CodeContext(
                    notebook=self._notebook.name,
                    path=str(self._notebook),
                    cell=cell["id"],
                    cell_number=f"#{cell['_index']}",
                    cell_source=code,
                )
                await self.execute_cell(session, code, cell_id, ctx)
                if not await self.execution_idle():
                    break

            self.logger.info(f"Success running notebook {self._notebook.name}")
            if not self._notebook_paths:
                self.logger.info("Done with this cycle of notebooks")
            if self.stopping:
                break

    async def execute_cell(
        self,
        session: JupyterLabSession,
        code: str,
        cell_id: str,
        context: CodeContext | None = None,
    ) -> None:
        if not self._notebook:
            raise RuntimeError("Executing a cell without a notebook")
        self.logger.info(f"Executing cell {cell_id}:\n{code}\n")
        with self.timings.start("execute_cell", self.annotations(cell_id)):
            self._running_code = code
            reply = await session.run_python(code, context=context)
            self._running_code = None
        self.logger.info(f"Result:\n{reply}\n")

    def dump(self) -> NotebookRunnerData:
        return NotebookRunnerData(
            notebook=self._notebook.name if self._notebook else None,
            running_code=self._running_code,
            **super().dump().model_dump(),
        )
