"""Helpers to pick which notebooks in a repo to execute."""

import json
from pathlib import Path

from structlog.stdlib import BoundLogger

from mobu.exceptions import NotebookRepositoryError
from mobu.models.repo import RepoConfig

from ..models.business.notebookrunner import NotebookMetadata


class NotebookFinder:
    """A helper to select which notebooks to execute based on config.

    This config can come from many places, like flock config, or an in-repo
    config file.

    Parameters
    ----------
    repo_path
        The local path on disk of a cloned repository of notebooks
    repo_config
        Config from a config file in the notebook repo
    exclude_dirs
        DEPRECATED: A set of paths relative to the repo root in which any
        descendant notebooks will not be executed
    exclude_patterns
        Notebooks that match these patterns will NOT be considered
    include_patterns
        Notebooks that match ANY of these patterns will be considered
    only_patterns
        Only Notebooks that match ALL of these patterns will NOT be considered
    available_services
        A list of Phalanx services that are available in the environment
    logger
        A structlog logger
    """

    def __init__(
        self,
        *,
        repo_path: Path,
        repo_config: RepoConfig,
        exclude_dirs: set[Path] | None = None,
        exclude_patterns: set[str] | None = None,
        include_patterns: set[str] | None = None,
        only_patterns: set[str] | None = None,
        available_services: set[str] | None = None,
        logger: BoundLogger,
    ) -> None:
        # In-repo config takes precedence
        exclude_dirs = repo_config.exclude_dirs or exclude_dirs or set()
        exclude_patterns = (
            repo_config.exclude_patterns or exclude_patterns or set()
        )
        include_patterns = (
            repo_config.include_patterns or include_patterns or set()
        )
        only_patterns = repo_config.only_patterns or only_patterns or set()
        available_services = available_services or set()

        if exclude_dirs:
            logger.info(
                "exclude_dirs is deprecated, use include_patterns and"
                " exclude_patterns instead. Merging exclude_dirs with"
                " exclude_patterns."
            )
            converted = {str(path / "**") for path in exclude_dirs}
            exclude_patterns = exclude_patterns | converted

        self._repo_path = repo_path
        self._exclude_dirs = exclude_dirs
        self._exclude_patterns = exclude_patterns
        self._include_patterns = include_patterns
        self._only_patterns = only_patterns
        self._available_services = available_services

        self._logger = logger.bind(
            repo_path=self._repo_path,
            repo_config=repo_config.model_dump(),
            exclude_dirs=self._exclude_dirs,
            exclude_patterns=self._exclude_patterns,
            include_patterns=self._include_patterns,
            only_patterns=self._only_patterns,
            available_services=self._available_services,
        )

    def find(self) -> set[Path]:
        """Return a list of notebooks to execute.

        * Start with all of the notebooks
        * If there are any union patterns, filter to any notebook that matches
          any of those patterns
        * Remove any notebook that matches any exclude pattern
        * Remove any notebook that declares a dependency on a Phalanx service
          that is not available
        * If intersect patterns are specified, remove any notebook that does
          not match an intersect pattern.
        """
        all_ = self._all()

        include = self._match_include(all_)
        only = self._match_only(all_)
        exclude = self._match_exclude()
        exclude_by_service = self._excluded_by_service()

        notebooks = (include - exclude - exclude_by_service) & only

        if not notebooks:
            self._logger.warning("No notebooks to run after filtering!")

        return notebooks

    def _all(self) -> set[Path]:
        return set(self._repo_path.glob("**/*.ipynb"))

    def _match_include(self, default: set[Path]) -> set[Path]:
        """Return notebooks that match any include pattern."""
        if not self._include_patterns:
            return default
        return set().union(
            *[
                self._repo_path.glob(pattern)
                for pattern in self._include_patterns
            ]
        )

    def _match_exclude(self) -> set[Path]:
        """Return notebooks that match any exclude pattern."""
        return set().union(
            *[
                self._repo_path.glob(pattern)
                for pattern in self._exclude_patterns
            ]
        )

    def _match_only(self, starting: set[Path]) -> set[Path]:
        """Return notebooks that match all only patterns."""
        if not self._only_patterns:
            return starting
        return starting.intersection(
            *[self._repo_path.glob(pattern) for pattern in self._only_patterns]
        )

    def _excluded_by_service(self) -> set[Path]:
        """Return notebooks that require unavailable services."""
        notebooks = self._repo_path.glob("**/*.ipynb")
        excluded: set[Path] = set()
        for notebook in notebooks:
            # Read Notebook Metadata
            try:
                notebook_text = notebook.read_text()
                notebook_json = json.loads(notebook_text)
                contents = notebook_json["metadata"].get("mobu", {})
                metadata = NotebookMetadata.model_validate(contents)
            except Exception as e:
                msg = f"Invalid notebook metadata {notebook.name}: {e!s}"
                raise NotebookRepositoryError(msg) from e

            missing_services = (
                metadata.required_services - self._available_services
            )
            if missing_services:
                msg = "Environment does not provide required services"
                self._logger.info(
                    msg,
                    notebook=notebook,
                    required_services=metadata.required_services,
                    missing_services=missing_services,
                )
                excluded.add(notebook)
        self._logger.info(
            "Excluding notebooks because of missing services",
            matched=excluded,
        )
        return excluded
