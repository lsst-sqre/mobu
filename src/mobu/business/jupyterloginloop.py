"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from mobu.business.base import Business
from mobu.jupyterclient import JupyterClient

if TYPE_CHECKING:
    from typing import Any, Dict

    from structlog import BoundLogger

    from ..user import User

__all__ = ["JupyterLoginLoop"]


class JupyterLoginLoop(Business):
    """Business that logs on to the hub, creates a lab, and deletes it."""

    def __init__(
        self, logger: BoundLogger, options: Dict[str, Any], user: User
    ) -> None:
        super().__init__(logger, options, user)
        self.success_count = 0
        self.failure_count = 0
        self._client = JupyterClient(user, logger, options)

    async def run(self) -> None:
        try:
            self.logger.info("Starting up...")
            self.start_event("hub_login")
            await self._client.hub_login()
            self.stop_current_event()
            while True:
                self.logger.info("Starting next iteration")
                self.start_event("ensure_lab")
                await self._client.ensure_lab()
                self.stop_current_event()
                self.logger.info("Lab created.")
                self.start_event("lab_wait")
                await asyncio.sleep(60)
                self.stop_current_event()
                self.logger.info("Deleting lab.")
                self.start_event("delete_lab")
                await self._client.delete_lab()
                self.stop_current_event()
                self.success_count += 1
                self.logger.info("Lab successfully deleted.")
                self.start_event("no_lab_wait")
                await asyncio.sleep(60)
                self.stop_current_event()
        except Exception:
            self.failure_count += 1
            raise

    async def stop(self) -> None:
        self.start_event("delete_lab_on_stop")
        await self._client.delete_lab()
        self.stop_current_event()

    def dump(self) -> Dict[str, Any]:
        r = super().dump()
        r.update(
            {
                "failure_count": self.failure_count,
                "success_count": self.success_count,
            }
        )
        return r
