"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new
jupyter labs on a nublado instance, and then delete it."""

__all__ = [
    "JupyterLoginLoop",
]

import asyncio
from dataclasses import dataclass, field

from mobu.business import Business
from mobu.jupyterclient import JupyterClient


@dataclass
class JupyterLoginLoop(Business):
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

            await self._client.hub_login()
            logger.info("Logged into hub")

            while True:
                logger.info("Starting next iteration")
                await self._client.ensure_lab()
                logger.info("Lab created.")
                await asyncio.sleep(60)
                logger.info("Deleting lab.")
                await self._client.delete_lab()
                self.success_count += 1
                logger.info("Lab successfully deleted.")
                await asyncio.sleep(60)
        except Exception:
            self.failure_count += 1
            raise

    def dump(self) -> dict:
        return {
            "name": "JupyterLoginLoop",
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "jupyter_client": self._client.dump(),
        }
