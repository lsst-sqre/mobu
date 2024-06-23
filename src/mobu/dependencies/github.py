"""Dependencies GitHub CI app functionality."""

from pathlib import Path

import yaml

from ..models.github import GitHubConfig
from ..models.user import User
from ..services.github_ci.ci_manager import CiManager
from .context import ContextDependency

__all__ = ["GitHubConfigDependency", "CiManagerDependency"]


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


class CiManagerDependency:
    """A process-global object to manage background CI workers.

    It is important to close this when Mobu shuts down to make sure that
    GitHub PRs that use the mobu CI app functionality don't have stuck
    check runs.
    """

    def __init__(self) -> None:
        self._ci_manager: CiManager | None = None

    def __call__(self) -> CiManager:
        return self.ci_manager

    async def initialize(
        self, base_context: ContextDependency, users: list[User]
    ) -> None:
        self._ci_manager = CiManager(
            users=users,
            http_client=base_context.process_context.http_client,
            gafaelfawr_storage=base_context.process_context.gafaelfawr,
            logger=base_context.process_context.logger,
        )

    @property
    def ci_manager(self) -> CiManager:
        if not self._ci_manager:
            raise RuntimeError("CiManagerDependency not initialized")
        return self._ci_manager

    async def aclose(self) -> None:
        if self._ci_manager:
            await self._ci_manager.aclose()
        self._ci_manager = None


class MaybeCiManagerDependency:
    """Try to return a CiManager, but don't blow up if it's not there.

    Used in external routes that return info about mobu, and may be called on
    installations that do not have the github ci functionality enabled.
    """

    def __init__(self, dep: CiManagerDependency) -> None:
        self.dep = dep

    def __call__(self) -> CiManager | None:
        try:
            return self.dep.ci_manager
        except RuntimeError:
            return None


github_config_dependency = GitHubConfigDependency()
ci_manager_dependency = CiManagerDependency()
maybe_ci_manager_dependency = MaybeCiManagerDependency(ci_manager_dependency)
