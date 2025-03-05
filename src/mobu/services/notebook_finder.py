"""Helpers to pick which notebooks in a repo to execute."""

import json
from pathlib import Path

from structlog.stdlib import BoundLogger

from mobu.exceptions import NotebookRepositoryError

from ..models.business.notebookrunner import (
    NotebookFilterResults,
    NotebookMetadata,
)


class NotebookFinder:
    """A helper to select which notebooks to execute based on config.

    This config can come from many places, like flock config, or an in-repo
    config file.

    Parameters
    ----------
    repo_path
        The local path on disk of a cloned repository of notebooks.
    exclude_paths
        A set of paths in which any descendant notebooks will not be executed.
    notebooks_to_run
        A list of notebooks that will be considered for execution. If this is
        None, then all notebooks in the repo will be considered.
    available_services
        A list of Phalanx services that are available in the environment.
    logger
        A structlog logger
    """

    def __init__(
        self,
        *,
        repo_path: Path,
        exclude_paths: set[Path],
        notebooks_to_run: list[Path] | None,
        available_services: set[str],
        logger: BoundLogger,
    ) -> None:
        self._repo_path = repo_path
        self._exclude_paths = exclude_paths
        self._notebooks_to_run = notebooks_to_run
        self._available_services = available_services
        self._logger = logger.bind(
            repo_path=self._repo_path,
            exclude_paths=self._exclude_paths,
            notebooks_to_run=self._notebooks_to_run,
        )

    def find(self) -> NotebookFilterResults:
        """Return a list of notebooks to execute.

        If a list of starting notebooks was provided at construction, then the
        starting list of candiates is those notebooks. Otherwise, all notebooks
        in the repo will be considered.

        Notebooks in the starting list will be excluded if:
        * They are descendants of specifically excluded directories
        * They list required services in their metadata and any of those
          services are not provided in the current environment
        """
        all_notebooks = set(self._repo_path.glob("**/*.ipynb"))
        if not all_notebooks:
            msg = "No notebooks found in {self._repo_dir}"
            raise NotebookRepositoryError(msg)

        results = NotebookFilterResults(all=all_notebooks)
        results.excluded_by_dir = {
            n for n in results.all if self._excluded_by_dir(n)
        }
        results.excluded_by_service = {
            n for n in results.all if self._excluded_by_service(n)
        }

        results.excluded_by_requested = self._excluded_by_requested(
            results.all
        )

        results.runnable = (
            results.all
            - results.excluded_by_service
            - results.excluded_by_dir
            - results.excluded_by_requested
        )
        if bool(results.runnable):
            self._logger.info(
                "Found notebooks to run",
                filter_results=results.model_dump(),
            )
        else:
            self._logger.warning(
                "No notebooks to run after filtering!",
                filter_results=results.model_dump(),
            )

        return results

    def _excluded_by_dir(self, notebook: Path) -> bool:
        # A notebook is excluded if any of its parent directories are excluded
        return bool(set(notebook.parents) & self._exclude_paths)

    def _excluded_by_service(self, notebook: Path) -> bool:
        """Return True if a notebook declares required services and they are
        available.
        """
        metadata = self._read_notebook_metadata(notebook)
        missing_services = (
            metadata.required_services - self._available_services
        )
        if missing_services:
            msg = "Environment does not provide required services for notebook"
            self._logger.info(
                msg,
                notebook=notebook,
                required_services=metadata.required_services,
                missing_services=missing_services,
            )
            return True
        return False

    def _excluded_by_requested(self, all: set[Path]) -> set[Path]:
        if not self._notebooks_to_run:
            return set()

        requested = {
            self._repo_path / notebook for notebook in self._notebooks_to_run
        }
        not_found = requested - all
        if not_found:
            msg = (
                "Requested notebooks do not exist in"
                f" {self._repo_path}: {not_found}"
            )
            raise NotebookRepositoryError(msg)
        return all - requested

    def _read_notebook_metadata(self, notebook: Path) -> NotebookMetadata:
        try:
            notebook_text = notebook.read_text()
            notebook_json = json.loads(notebook_text)
            metadata = notebook_json["metadata"].get("mobu", {})
            return NotebookMetadata.model_validate(metadata)
        except Exception as e:
            msg = f"Invalid notebook metadata {notebook.name}: {e!s}"
            raise NotebookRepositoryError(msg) from e
