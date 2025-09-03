"""NotebookRunner logic for mobu.

This business pattern will clone a Git repo full of notebooks, iterate through
the notebooks, and run them on the remote Nublado lab.
"""

import contextlib
import json
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
    NotebookRunnerData,
    NotebookRunnerOptions,
)
from ...models.repo import RepoConfig
from ...models.user import AuthenticatedUser
from ...sentry import capturing_start_span, start_transaction
from ...services.business.base import CommonEventAttrs
from ...services.notebook_finder import NotebookFinder
from ...services.repo import RepoManager
from .nublado import NubladoBusiness

__all__ = ["ExecutionIteration", "NotebookRunner"]


class _CommonNotebookEventAttrs(CommonEventAttrs):
    """Common notebook event attributes."""

    notebook: str
    repo: str
    repo_ref: str
    repo_hash: str


@dataclass(frozen=True)
class ExecutionIteration:
    """Properties of a set of notebook executions."""

    iterator: Iterator[int]
    size: int | str


class NotebookRunner[T: NotebookRunnerOptions](ABC, NubladoBusiness):
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
        options: T,
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
        self._running_code: str | None = None
        self._repo_manager = repo_manager
        self._repo_config: RepoConfig | None = None

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
                username=self.user.username,
            )
        self._repo_path = None
        self._repo_hash = None
        self._notebook = None
        self._notebook_paths = None
        self._running_code = None

    async def initialize(self) -> None:
        """Prepare to run the business.

        * Get notebook repo files from the repo manager
        * Parse the in-repo config
        * Filter the notebooks
        """
        info = await self._repo_manager.clone(
            url=self.options.repo_url,
            ref=self.options.repo_ref,
            username=self.user.username,
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
        self._repo_config = repo_config

        self._notebooks = self.find_notebooks()
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

    def find_notebooks(self) -> set[Path]:
        with capturing_start_span(op="find_notebooks"):
            if self._repo_path is None:
                raise NotebookRepositoryError(
                    "Repository directory must be set", self.user.username
                )
            if self._repo_config is None:
                raise NotebookRepositoryError(
                    "Repo config must be parsed", self.user.username
                )
            finder = NotebookFinder(
                repo_path=self._repo_path,
                repo_config=self._repo_config,
                exclude_dirs=self.options.exclude_dirs,
                collection_rules=self.options.collection_rules,
                available_services=self._config.available_services,
                logger=self.logger,
            )
            return finder.find()

    def next_notebook(self) -> Path:
        if not self._notebooks:
            self._notebooks = self.find_notebooks()
        if not self._notebook_paths:
            self._notebook_paths = list(self._notebooks)
            random.shuffle(self._notebook_paths)
        return self._notebook_paths.pop()

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
        iterator = self.execution_iterator()
        for count in iterator.iterator:
            iteration = f"{count + 1}/{iterator.size}"
            if self.refreshing:
                await self.refresh()
                return
            await self.execute_notebook(session, iteration)

            if self.stopping:
                break

    @abstractmethod
    def execution_iterator(self) -> ExecutionIteration:
        """Return an iterator to control sets of code executions."""

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
        self, session: JupyterLabSession, iteration: str
    ) -> None:
        self._notebook = self.next_notebook()
        relative_notebook = self._relative_notebook()
        logger = self.logger.bind(notebook=relative_notebook)
        msg = f"Notebook {self._notebook.name} iteration {iteration}"
        logger.info(msg)

        with self.trace_notebook(
            notebook=relative_notebook, iteration=iteration
        ) as span:
            try:
                cells = self.read_notebook(self._notebook)

                # We want to wait if the notebook is totally empty so we don't
                # spin out of control on empty notebooks
                logger.warning("empty notebook")
                if not cells:
                    await self.execution_idle()
                for cell in cells:
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

        logger.info(f"Success running notebook {self._notebook.name}")
        await self._publish_notebook_event(
            duration=duration(span), success=True
        )
        if not self._notebook_paths:
            self.logger.info("Done with this cycle of notebooks")
        await self.notebook_idle()

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

    async def notebook_idle(self) -> bool:
        """Pause between each notebook execution."""
        idle_time = self.options.notebook_idle_time
        self.logger.debug("notebook_idle", idle_time=idle_time)
        with capturing_start_span(op="notebook_idle"):
            return await self.pause(idle_time)

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
