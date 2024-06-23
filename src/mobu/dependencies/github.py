"""Dependencies GitHub CI app functionality."""

from pathlib import Path

import yaml

from ..models.github import GitHubConfig


class GitHubConfigDependency:
    """Holds the config for GitHub app integration, loaded from a file."""

    def __init__(self) -> None:
        self._config: GitHubConfig | None = None

    def __call__(self) -> GitHubConfig:
        return self.config

    @property
    def config(self) -> GitHubConfig:
        if not self._config:
            raise RuntimeError("GitHubConfigDependency not initialized")
        return self._config

    def initialize(self, path: Path) -> None:
        self._config = GitHubConfig.model_validate(
            yaml.safe_load(path.read_text())
        )


github_config_dependency = GitHubConfigDependency()
