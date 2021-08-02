"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

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

    This class modifies the core `~mobu.business.base.Business` loop by
    providing the overall ``execute`` framework and defualt ``startup`` and
    ``shutdown`` methods.  It will log on to JupyterHub, ensure no lab
    currently exists, create a lab, run ``lab_business``, and then shut down
    the lab before starting another iteration.

    Subclasses should override ``lab_business`` to do whatever they want to do
    inside a lab.  The default behavior just waits for ``login_idle_time``.

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

    async def close(self) -> None:
        await self._client.close()

    async def startup(self) -> None:
        await self.hub_login()
        await self.initial_delete_lab()

    async def execute(self) -> None:
        """The work done in each iteration of the loop."""
        await self.ensure_lab()
        await self.lab_settle()
        if self.stopping:
            return
        await self.lab_login()
        await self.lab_business()
        if self.config.delete_lab:
            await self.hub_login()
            await self.delete_lab()

    async def shutdown(self) -> None:
        await self.delete_lab()

    async def hub_login(self) -> None:
        self.logger.info("Logging in to hub")
        with self.timings.start("hub_login"):
            await self._client.hub_login()

    async def ensure_lab(self) -> None:
        with self.timings.start("ensure_lab"):
            await self._client.ensure_lab()

    async def lab_settle(self) -> None:
        with self.timings.start("lab_settle"):
            await self.pause(self.config.settle_time)

    async def lab_login(self) -> None:
        with self.timings.start("lab_login"):
            await self._client.lab_login()

    async def delete_lab(self) -> None:
        self.logger.info("Deleting lab")
        with self.timings.start("delete_lab"):
            await self._client.delete_lab()
        self.logger.info("Lab successfully deleted")

    async def initial_delete_lab(self) -> None:
        self.logger.info("Deleting any existing lab")
        with self.timings.start("initial_delete_lab"):
            await self._client.delete_lab()

    async def lab_business(self) -> None:
        """Do whatever business we want to do inside a lab.

        Placeholder function intended to be overridden by subclasses.  The
        default behavior is to wait a minute and then shut the lab down
        again.
        """
        with self.timings.start("lab_wait"):
            await self.pause(self.config.login_idle_time)
