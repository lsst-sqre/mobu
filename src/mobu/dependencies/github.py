"""Dependencies GitHub CI app functionality."""

from pathlib import Path

import yaml

from ..github_config import GitHubCiAppConfig, GitHubRefreshAppConfig
from ..models.user import User
from ..services.github_ci.ci_manager import CiManager
from .context import ContextDependency


class GitHubCiAppConfigDependency:
    """Config for GitHub CI app integration, loaded from a file."""

    def __init__(self) -> None:
        self.config: GitHubCiAppConfig

    def __call__(self) -> GitHubCiAppConfig:
        return self.config

    def initialize(self, path: Path) -> None:
        self.config = GitHubCiAppConfig.model_validate(
            yaml.safe_load(path.read_text())
        )


class GitHubRefreshAppConfigDependency:
    """Config for GitHub refresh app integration, loaded from a
    file.
    """

    def __init__(self) -> None:
        self.config: GitHubRefreshAppConfig

    def __call__(self) -> GitHubRefreshAppConfig:
        return self.config

    def initialize(self, path: Path) -> None:
        self.config = GitHubRefreshAppConfig.model_validate(
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

    @property
    def ci_manager(self) -> CiManager:
        if self._ci_manager is None:
            raise RuntimeError("CiManager has not been initialized yet")
        return self._ci_manager

    def __call__(self) -> CiManager:
        return self.ci_manager

    def initialize(
        self, base_context: ContextDependency, users: list[User]
    ) -> None:
        self._ci_manager = CiManager(
            users=users,
            http_client=base_context.process_context.http_client,
            gafaelfawr_storage=base_context.process_context.gafaelfawr,
            logger=base_context.process_context.logger,
        )

    async def aclose(self) -> None:
        if self._ci_manager is not None:
            await self._ci_manager.aclose()


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


github_refresh_app_config_dependency = GitHubRefreshAppConfigDependency()
github_ci_app_config_dependency = GitHubCiAppConfigDependency()
ci_manager_dependency = CiManagerDependency()
maybe_ci_manager_dependency = MaybeCiManagerDependency(ci_manager_dependency)
