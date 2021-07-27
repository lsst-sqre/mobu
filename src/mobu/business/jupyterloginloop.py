"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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
        self._last_login = datetime.fromtimestamp(0, tz=timezone.utc)

    async def run(self) -> None:
        self.logger.info("Starting up...")
        await self.startup()
        while True:
            await self.reauth_if_needed()
            self.logger.info("Starting next iteration")
            try:
                await self.ensure_lab()
                await self.lab_business()
                await self.delete_lab()
                self.success_count += 1
            except Exception:
                self.failure_count += 1
                raise
            await self.lab_idle()

    async def startup(self) -> None:
        """Run before the start of the first iteration and then not again."""
        await self.hub_login()

    async def hub_login(self) -> None:
        with self.timings.start("hub_login"):
            await self._client.hub_login()
            self._last_login = self._now()

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
        with self.timings.start("lab_wait"):
            await asyncio.sleep(5)

    async def lab_idle(self) -> None:
        """Executed at the end of each iteration for a given lab.

        Intended to be overridden by subclasses if they want different idle
        behavior.
        """
        delay = self.config.lab_idle_time
        if delay > 0:
            with self.timings.start("idle"):
                await asyncio.sleep(delay)

    async def execution_idle(self) -> None:
        """Executed between each unit of work execution (usually a Lab
        cell).
        """
        delay = self.config.execution_idle_time
        if delay > 0:
            with self.timings.start("execution_idle"):
                await asyncio.sleep(self.config.execution_idle_time)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def reauth_if_needed(self) -> None:
        now = self._now()
        elapsed = now - self._last_login
        if elapsed > timedelta(self.config.reauth_interval):
            await self.hub_reauth()

    async def hub_reauth(self) -> None:
        self.logger.info("Reauthenticating to Hub")
        with self.timings.start("hub_reauth"):
            await self._client.hub_login()

    async def stop(self) -> None:
        with self.timings.start("delete_lab_on_stop"):
            await self._client.delete_lab()
        await self._client.close()
