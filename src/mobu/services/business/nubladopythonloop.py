"""NubladoPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from __future__ import annotations

from datetime import timedelta

import sentry_sdk
from rubin.nublado.client import JupyterLabSession
from safir.sentry import duration
from structlog.stdlib import BoundLogger

from ...events import Events, NubladoPythonExecution
from ...models.business.nubladopythonloop import NubladoPythonLoopOptions
from ...models.user import AuthenticatedUser
from ...sentry import start_transaction
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

    async def execute_code(self, session: JupyterLabSession) -> None:
        code = self.options.code
        sentry_sdk.set_context("code_info", {"code": code})
        for _count in range(self.options.max_executions):
            with start_transaction(
                name=f"{self.name} - Execute Python",
                op="mobu.notebookrunner.execute_python",
            ) as span:
                try:
                    reply = await session.run_python(code)
                except Exception:
                    await self._publish_failure(code=code)
                    raise
            self.logger.info(f"{code} -> {reply}")
            await self._publish_success(code=code, duration=duration(span))
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
