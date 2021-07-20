"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..jupyterclient import JupyterClient
from .base import Business

if TYPE_CHECKING:
    from typing import Any, Dict

    from structlog import BoundLogger

    from ..user import User

__all__ = ["JupyterLoginLoop"]


class JupyterLoginLoop(Business):
    """Business that logs on to the hub, creates a lab, and deletes it.

    Once this business has been stopped, it cannot be started again (the
    `aiohttp.ClientSession` will be closed), and the instance should be
    dropped after retrieving any status information.
    """

    def __init__(
        self, logger: BoundLogger, options: Dict[str, Any], user: User
    ) -> None:
        super().__init__(logger, options, user)
        self._client = JupyterClient(user, logger, options)

    async def run(self) -> None:
        self.logger.info("Starting up...")
        await self.startup()
        while True:
            self.logger.info("Starting next iteration")
            try:
                await self.ensure_lab()
                await self.lab_business()
                await self.delete_lab()
                self.success_count += 1
            except Exception:
                self.failure_count += 1
                raise
            await self.idle()

    async def startup(self) -> None:
        """Run before the start of the first iteration and then not again."""
        await self.hub_login()

    async def hub_login(self) -> None:
        self.start_event("hub_login")
        await self._client.hub_login()
        self.stop_current_event()

    async def ensure_lab(self) -> None:
        self.start_event("ensure_lab")
        await self._client.ensure_lab()
        self.stop_current_event()
        self.logger.info("Lab created.")

    async def delete_lab(self) -> None:
        self.logger.info("Deleting lab.")
        self.start_event("delete_lab")
        await self._client.delete_lab()
        self.stop_current_event()
        self.logger.info("Lab successfully deleted.")

    async def lab_business(self) -> None:
        """Do whatever business we want to do inside a lab.

        Placeholder function intended to be overridden by subclasses.
        """
        self.start_event("lab_wait")
        await asyncio.sleep(60)
        self.stop_current_event()

    async def idle(self) -> None:
        """Executed at the end of each iteration.

        Intended to be overridden by subclasses if they want different idle
        behavior.
        """
        self.start_event("no_lab_wait")
        await asyncio.sleep(60)
        self.stop_current_event()

    async def stop(self) -> None:
        self.start_event("delete_lab_on_stop")
        await self._client.delete_lab()
        self.stop_current_event()
        await self._client.close()
