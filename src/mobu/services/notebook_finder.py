"""Helpers to pick which notebooks in a repo to execute."""

import json
from pathlib import Path

from structlog.stdlib import BoundLogger

from ..exceptions import NotebookRepositoryError
from ..models.business.notebookrunner import CollectionRule, NotebookMetadata
from ..models.repo import RepoConfig

__all__ = ["NotebookFinder"]


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
    collection_rules
        A set of rules describing which notebooks in a repo to run
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
        collection_rules: list[CollectionRule] | None = None,
        available_services: set[str] | None = None,
        logger: BoundLogger,
    ) -> None:
        # Merge in-repo config
        exclude_dirs = exclude_dirs or set()
        exclude_dirs = exclude_dirs.union(repo_config.exclude_dirs)

        collection_rules = collection_rules or []
        collection_rules += repo_config.collection_rules

        if exclude_dirs:
            logger.warning(
                "exclude_dirs is deprecated, use collection_rules instead."
                " Merging exclude_dirs with collection_rules."
            )
            converted = {str(path / "**") for path in exclude_dirs}
            collection_rules.append(
                CollectionRule(type="exclude_union_of", patterns=converted)
            )

        self._collection_rules = collection_rules
        self._available_services = available_services or set()
        self._repo_path = repo_path

        self._logger = logger.bind(
            repo_path=self._repo_path,
            collection_rules=self._collection_rules,
            available_services=self._available_services,
        )

    def find(self) -> set[Path]:
        """Return a list of notebooks to execute.

        * Start with all notebooks in the repo.
        * For each collection rule, remove notebooks:

          * Intersect rules will remove notebooks that are not in the \
            intersection of:

              * The current set
              * The union of the matched patterns.

          * Exclude rules will remove notebooks from the current set that are \
            in the union of the matched patterns.

        * Remove any remaining notebooks that require unavailable services.
        """
        notebooks = set(self._repo_path.glob("**/*.ipynb"))

        for rule in self._collection_rules:
            collected = self._collect(rule.patterns)
            match rule.type:
                case "intersect_union_of":
                    notebooks = notebooks.intersection(collected)
                case "exclude_union_of":
                    notebooks = notebooks.difference(collected)

        notebooks = notebooks - self._excluded_by_service()

        if not notebooks:
            self._logger.warning("No notebooks to run after filtering!")

        return notebooks

    def _collect(self, patterns: set[str]) -> set[Path]:
        """Find any notebook that matches any pattern."""
        collected: set[Path] = set()
        for pattern in patterns:
            matched = self._repo_path.glob(pattern)
            collected = collected.union(matched)
        return collected

    def _excluded_by_service(self) -> set[Path]:
        """Return notebooks that require unavailable services."""
        notebooks = self._repo_path.glob("**/*.ipynb")
        excluded: set[Path] = set()
        for notebook in notebooks:
            metadata = self._read_notebook_metadata(notebook)
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
        return excluded

    def _read_notebook_metadata(self, notebook: Path) -> NotebookMetadata:
        try:
            notebook_text = notebook.read_text()
            notebook_json = json.loads(notebook_text)
            metadata = notebook_json["metadata"].get("mobu", {})
            return NotebookMetadata.model_validate(metadata)
        except Exception as e:
            msg = f"Invalid notebook metadata {notebook.name}: {e!s}"
            raise NotebookRepositoryError(msg) from e
