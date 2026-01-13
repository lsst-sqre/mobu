"""Dependencies GitHub CI app functionality."""

from ..models.user import User
from ..services.github_ci.ci_manager import CiManager
from ..storage.gafaelfawr import GafaelfawrStorage
from .config import config_dependency
from .context import ContextDependency

__all__ = ["CiManagerDependency", "MaybeCiManagerDependency"]


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
        self,
        *,
        base_context: ContextDependency,
        users: list[User],
        github_app_id: int,
        github_private_key: str,
        scopes: list[str],
    ) -> None:
        gafaelfawr_storage = GafaelfawrStorage(
            config_dependency.config,
            base_context.process_context.gafaelfawr,
            base_context.process_context.logger,
        )
        self._ci_manager = CiManager(
            users=users,
            github_app_id=github_app_id,
            github_private_key=github_private_key,
            scopes=scopes,
            discovery_client=base_context.process_context.discovery_client,
            http_client=base_context.process_context.http_client,
            events=base_context.process_context.events,
            repo_manager=base_context.process_context.repo_manager,
            gafaelfawr_storage=gafaelfawr_storage,
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


ci_manager_dependency = CiManagerDependency()
maybe_ci_manager_dependency = MaybeCiManagerDependency(ci_manager_dependency)
