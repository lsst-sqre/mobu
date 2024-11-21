"""NubladoPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from rubin.nublado.client import JupyterLabSession
from structlog.stdlib import BoundLogger

from ...events import Events, NubladoPythonExecution
from ...models.business.nubladopythonloop import NubladoPythonLoopOptions
from ...models.user import AuthenticatedUser
from .nublado import NubladoBusiness

__all__ = ["NubladoPythonLoop"]


class NubladoPythonLoop(NubladoBusiness):
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
    flock
        Flock that is running this business, if it is running in a flock.
    """

    def __init__(
        self,
        *,
        options: NubladoPythonLoopOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        events: Events,
        logger: BoundLogger,
        flock: str | None,
    ) -> None:
        super().__init__(
            options=options,
            user=user,
            http_client=http_client,
            events=events,
            logger=logger,
            flock=flock,
        )

    async def execute_code(self, session: JupyterLabSession) -> None:
        code = self.options.code
        for _count in range(self.options.max_executions):
            with self.timings.start("execute_code", self.annotations()) as sw:
                try:
                    reply = await session.run_python(code)
                except:
                    await self._publish_failure(code=code)
                    raise
            self.logger.info(f"{code} -> {reply}")
            await self._publish_success(code=code, duration=sw.elapsed)
            if not await self.execution_idle():
                break

    async def _publish_success(self, code: str, duration: timedelta) -> None:
        await self.events.nublado_python_execution.publish(
            NubladoPythonExecution(
                duration=duration,
                code=code,
                success=True,
                **self.common_event_attrs(),
            )
        )

    async def _publish_failure(self, code: str) -> None:
        await self.events.nublado_python_execution.publish(
            NubladoPythonExecution(
                duration=None,
                code=code,
                success=False,
                **self.common_event_attrs(),
            )
        )
