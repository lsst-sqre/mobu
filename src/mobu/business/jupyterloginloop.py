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
    from structlog import BoundLogger

    from ..models.business import BusinessConfig
    from ..user import AuthenticatedUser

__all__ = ["JupyterLoginLoop"]


class JupyterLoginLoop(Business):
    """Business that logs on to the hub, creates a lab, and deletes it.

    Once this business has been stopped, it cannot be started again (the
    `aiohttp.ClientSession` will be closed), and the instance should be
    dropped after retrieving any status information.
    """

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        self._client = JupyterClient(user, logger, business_config)

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
        with self.timings.start("hub_login"):
            await self._client.hub_login()

    async def ensure_lab(self) -> None:
        with self.timings.start("ensure_lab"):
            await self._client.ensure_lab()
        self.logger.info("Lab created.")

    async def delete_lab(self) -> None:
        self.logger.info("Deleting lab.")
        with self.timings.start("delete_lab"):
            await self._client.delete_lab()
        self.logger.info("Lab successfully deleted.")

    async def lab_business(self) -> None:
        """Do whatever business we want to do inside a lab.

        Placeholder function intended to be overridden by subclasses.
        """
        await self.idle()

    async def idle(self) -> None:
        """Executed at the end of each iteration.

        Intended to be overridden by subclasses if they want different idle
        behavior.
        """
        with self.timings.start("idle"):
            await asyncio.sleep(self.config.idle_time)

    async def stop(self) -> None:
        with self.timings.start("delete_lab_on_stop"):
            await self._client.delete_lab()
        await self._client.close()
