"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new
jupyter labs on a nublado instance, and then delete it."""

__all__ = [
    "JupyterLoginLoop",
]

import asyncio
from dataclasses import dataclass, field

from mobu.business.businesstime import BusinessTime
from mobu.jupyterclient import JupyterClient


@dataclass
class JupyterLoginLoop(BusinessTime):
    success_count: int = 0
    failure_count: int = 0
    _client: JupyterClient = field(init=False)

    async def run(self) -> None:
        try:
            logger = self.monkey.log
            logger.info("Starting up...")
            self._client = JupyterClient(
                self.monkey.user, logger, self.options
            )
            self.start_event("hub_login")
            await self._client.hub_login()
            self.stop_current_event()
            while True:
                logger.info("Starting next iteration")
                self.start_event("ensure_lab")
                await self._client.ensure_lab()
                self.stop_current_event()
                logger.info("Lab created.")
                self.start_event("lab_wait")
                await asyncio.sleep(60)
                self.stop_current_event()
                logger.info("Deleting lab.")
                self.start_event("delete_lab")
                await self._client.delete_lab()
                self.stop_current_event()
                self.success_count += 1
                logger.info("Lab successfully deleted.")
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

    def dump(self) -> dict:
        r = super().dump()
        r.update(
            {
                "name": "JupyterLoginLoop",
                "failure_count": self.failure_count,
                "success_count": self.success_count,
            }
        )
        return r
