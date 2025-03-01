"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Nublado lab.
"""

from __future__ import annotations

import contextlib
import json
import random
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, override

import sentry_sdk
import yaml
from rubin.nublado.client import JupyterLabSession
from rubin.nublado.client.exceptions import CodeExecutionError
from rubin.nublado.client.models import CodeContext
from safir.sentry import duration
from sentry_sdk import set_context, set_tag
from sentry_sdk.tracing import Span, Transaction
from structlog.stdlib import BoundLogger

from ...constants import GITHUB_REPO_CONFIG_PATH
from ...dependencies.config import config_dependency
from ...events import Events, NotebookCellExecution, NotebookExecution
from ...exceptions import (
    NotebookCellExecutionError,
    NotebookRepositoryError,
    RepositoryConfigError,
)
from ...models.business.notebookrunner import (
    ListNotebookRunnerOptions,
    NotebookFilterResults,
    NotebookMetadata,
    NotebookRunnerData,
    NotebookRunnerOptions,
)
from ...models.repo import RepoConfig
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from ...services.business.base import CommonEventAttrs
from ...services.repo import RepoManager
from .nublado import NubladoBusiness

__all__ = ["NotebookRunner"]


class _CommonNotebookEventAttrs(CommonEventAttrs):
    """Common notebook event attributes."""

    notebook: str
    repo: str
    repo_ref: str
    repo_hash: str


class NotebookRunner(NubladoBusiness):
    """Start a Jupyter lab and run a sequence of notebooks.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    events
        Event publishers.
    logger
        Logger to use to report the results of business.
    flock
        Flock that is running this business, if it is running in a flock.
    """

    def __init__(
        self,
        *,
        options: NotebookRunnerOptions | ListNotebookRunnerOptions,
        user: AuthenticatedUser,
        repo_manager: RepoManager,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            events=events,
            logger=logger,
            flock=flock,
        )
        self._config = config_dependency.config
        self._notebook: Path | None = None
        self._notebook_paths: list[Path] | None = None
        self._repo_path: Path | None = None
        self._repo_hash: str | None = None
        self._exclude_paths: set[Path] = set()
        self._running_code: str | None = None
        self._max_executions: int | None = None
        self._notebooks_to_run: list[Path] | None = None
        self._repo_manager = repo_manager

        match options:
            case NotebookRunnerOptions(max_executions=max_executions):
                self._max_executions = max_executions
            case ListNotebookRunnerOptions(notebooks_to_run=notebooks_to_run):
                self._notebooks_to_run = notebooks_to_run

    @override
    async def startup(self) -> None:
        await self.initialize()
        await super().startup()

    async def cleanup(self) -> None:
        if self._repo_hash is not None:
            await self._repo_manager.invalidate(
                url=self.options.repo_url,
                ref=self.options.repo_ref,
                repo_hash=self._repo_hash,
            )
        self._repo_path = None
        self._repo_hash = None
        self._notebook_filter_results = None

    async def initialize(self) -> None:
        """Prepare to run the business.

        * Get notebook repo files from the repo manager
        * Parse the in-repo config
        * Filter the notebooks
        """
        info = await self._repo_manager.clone(
            url=self.options.repo_url, ref=self.options.repo_ref
        )
        self._repo_path = info.path
        self._repo_hash = info.hash

        repo_config_path = self._repo_path / GITHUB_REPO_CONFIG_PATH
        set_context(
            "repo_info",
            {
                "repo_url": self.options.repo_url,
                "repo_ref": self.options.repo_ref,
                "repo_hash": self._repo_hash,
                "repo_config_file": GITHUB_REPO_CONFIG_PATH,
            },
        )
        if repo_config_path.exists():
            try:
                repo_config = RepoConfig.model_validate(
                    yaml.safe_load(repo_config_path.read_text())
                )
            except Exception as err:
                raise RepositoryConfigError(
                    f"Error parsing config file: {GITHUB_REPO_CONFIG_PATH}"
                ) from err
        else:
            repo_config = RepoConfig()

        exclude_dirs = repo_config.exclude_dirs
        self._exclude_paths = {self._repo_path / path for path in exclude_dirs}
        self._notebooks = self.find_notebooks()
        set_context(
            "notebook_filter_info", self._notebooks.model_dump(mode="json")
        )
        self.logger.info("Repository cloned and ready")

    @override
    async def shutdown(self) -> None:
        await self.cleanup()
        await super().shutdown()

    async def refresh(self) -> None:
        self.logger.info("Getting new notebooks and forcing new execution")
        await self.cleanup()
        await self.initialize()
        self.refreshing = False

    def is_excluded(self, notebook: Path) -> bool:
        # A notebook is excluded if any of its parent directories are excluded
        return bool(set(notebook.parents) & self._exclude_paths)

    def missing_services(self, notebook: Path) -> bool:
        """Return True if a notebook declares required services and they are
        available.
        """
        metadata = self.read_notebook_metadata(notebook)
        missing_services = (
            metadata.required_services - self._config.available_services
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
        with capturing_start_span(op="find_notebooks"):
            if self._repo_path is None:
                raise NotebookRepositoryError(
                    "Repository directory must be set", self.user.username
                )

            all_notebooks = set(self._repo_path.glob("**/*.ipynb"))
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
                    self._repo_path / notebook
                    for notebook in self._notebooks_to_run
                }
                not_found = requested - filter_results.all
                if not_found:
                    msg = (
                        "Requested notebooks do not exist in"
                        f" {self._repo_path}: {not_found}"
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
        with capturing_start_span(op="read_notebook_metadata"):
            try:
                notebook_text = notebook.read_text()
                notebook_json = json.loads(notebook_text)
                metadata = notebook_json["metadata"].get("mobu", {})
                return NotebookMetadata.model_validate(metadata)
            except Exception as e:
                msg = f"Invalid notebook metadata {notebook.name}: {e!s}"
                raise NotebookRepositoryError(msg, self.user.username) from e

    def read_notebook(self, notebook: Path) -> list[dict[str, Any]]:
        with capturing_start_span(op="read_notebook"):
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

    @override
    @asynccontextmanager
    async def open_session(
        self, notebook_name: str | None = None
    ) -> AsyncGenerator[JupyterLabSession]:
        """Override to add the notebook name."""
        if not notebook_name:
            notebook_name = self._notebook.name if self._notebook else None
        async with super().open_session(notebook_name) as session:
            yield session

    @override
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
            await self.execute_notebook(session, count, num_executions)

            if self.stopping:
                break

    @contextlib.contextmanager
    def trace_notebook(
        self, notebook: str, iteration: str
    ) -> Iterator[Transaction | Span]:
        """Set up tracing context for executing a notebook."""
        notebook_info = {"notebook": notebook, "iteration": iteration}
        with start_transaction(
            name=f"{self.name} - Execute notebook",
            op="mobu.notebookrunner.execute_notebook",
        ) as span:
            set_tag("notebook", notebook)
            set_context("notebook_info", notebook_info)
            yield span

    async def execute_notebook(
        self, session: JupyterLabSession, count: int, num_executions: int
    ) -> None:
        self._notebook = self.next_notebook()
        relative_notebook = self._relative_notebook()
        iteration = f"{count + 1}/{num_executions}"
        msg = f"Notebook {self._notebook.name} iteration {iteration}"
        self.logger.info(msg)

        with self.trace_notebook(
            notebook=relative_notebook, iteration=iteration
        ) as span:
            try:
                for cell in self.read_notebook(self._notebook):
                    code = "".join(cell["source"])
                    cell_id = cell.get("id") or cell["_index"]
                    ctx = CodeContext(
                        notebook=relative_notebook,
                        path=str(self._notebook),
                        cell=cell_id,
                        cell_number=f"#{cell['_index']}",
                        cell_source=code,
                    )
                    await self.execute_cell(session, code, cell_id, ctx)
                    if not await self.execution_idle():
                        break
            except:
                await self._publish_notebook_event(
                    duration=duration(span), success=False
                )
                raise

        self.logger.info(f"Success running notebook {self._notebook.name}")
        await self._publish_notebook_event(
            duration=duration(span), success=True
        )
        if not self._notebook_paths:
            self.logger.info("Done with this cycle of notebooks")

    async def _publish_notebook_event(
        self, duration: timedelta, *, success: bool
    ) -> None:
        await self.events.notebook_execution.publish(
            NotebookExecution(
                **self.common_notebook_event_attrs(),
                duration=duration,
                success=success,
            )
        )

    async def _publish_cell_event(
        self, *, cell_id: str, duration: timedelta, success: bool
    ) -> None:
        await self.events.notebook_cell_execution.publish(
            NotebookCellExecution(
                **self.common_notebook_event_attrs(),
                duration=duration,
                success=success,
                cell_id=cell_id,
            )
        )

    def common_notebook_event_attrs(self) -> _CommonNotebookEventAttrs:
        """Return notebook event attrs with the other common attrs."""
        return {
            **self.common_event_attrs(),
            "repo": self.options.repo_url,
            "repo_ref": self.options.repo_ref,
            "repo_hash": self._repo_hash or "unknown",
            "notebook": self._relative_notebook(),
        }

    async def execute_cell(
        self,
        session: JupyterLabSession,
        code: str,
        cell_id: str,
        context: CodeContext,
    ) -> None:
        if not self._notebook:
            raise RuntimeError("Executing a cell without a notebook")
        self.logger.info(f"Executing cell {cell_id}:\n{code}\n")
        set_tag("cell", cell_id)
        cell_info = {
            "code": code,
            "cell_id": cell_id,
            "cell_number": context.cell_number,
        }
        set_context("cell_info", cell_info)
        with capturing_start_span(op="execute_cell") as span:
            # The scope context only appears on the transaction, and not on
            # individual spans. Since the cell info will be different for
            # different spans, we need to set this data directly on the span.
            # We have to set it in the context too so that it shows up in any
            # exception events. Unfortuantely, span data is not included in
            # exception events.
            span.set_data("cell_info", cell_info)
            self._running_code = code
            try:
                reply = await session.run_python(code, context=context)
            except Exception as e:
                if isinstance(e, CodeExecutionError) and e.error:
                    sentry_sdk.get_current_scope().add_attachment(
                        filename="nublado_error.txt",
                        bytes=self.remove_ansi_escapes(e.error).encode(),
                    )
                await self._publish_cell_event(
                    cell_id=cell_id,
                    duration=duration(span),
                    success=False,
                )

                notebook = getattr(context, "notebook", "<unknown notebook")
                msg = f"{notebook}: Error executing cell"
                raise NotebookCellExecutionError(msg) from e

            self._running_code = None
        self.logger.info(f"Result:\n{reply}\n")
        await self._publish_cell_event(
            cell_id=cell_id, duration=duration(span), success=True
        )

    @override
    def dump(self) -> NotebookRunnerData:
        return NotebookRunnerData(
            notebook=self._notebook.name if self._notebook else None,
            running_code=self._running_code,
            **super().dump().model_dump(),
        )

    def _relative_notebook(self) -> str:
        """Give the path of the current notebook relative to the repo root."""
        if self._notebook is None or self._repo_path is None:
            return "unknown"
        return str(self._notebook.relative_to(self._repo_path))
