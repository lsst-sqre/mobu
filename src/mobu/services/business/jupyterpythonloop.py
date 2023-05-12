"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from __future__ import annotations

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...models.business.jupyterpythonloop import JupyterPythonLoopOptions
from ...models.user import AuthenticatedUser
from ...storage.jupyter import JupyterLabSession
from .nublado import NubladoBusiness

__all__ = ["JupyterPythonLoop"]


class JupyterPythonLoop(NubladoBusiness):
    """Run simple Python code in a loop inside a lab kernel.

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
        options: JupyterPythonLoopOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)

    async def execute_code(self, session: JupyterLabSession) -> None:
        code = self.options.code
        for _count in range(self.options.max_executions):
            with self.timings.start("execute_code", self.annotations()):
                reply = await session.run_python(code)
            self.logger.info(f"{code} -> {reply}")
            if not await self.execution_idle():
                break
