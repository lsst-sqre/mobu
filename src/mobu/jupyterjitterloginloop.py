"""JupyterJitterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new JupyterLab
instances on a nublado instance, with jitter built in to the timing,
and then delete those instances."""

__all__ = [
    "JupyterJitterLoginLoop",
]

import asyncio
import random
from dataclasses import dataclass

from mobu.jupyterclient import JupyterClient
from mobu.jupyterloginloop import JupyterLoginLoop


@dataclass
class JupyterJitterLoginLoop(JupyterLoginLoop):
    async def run(self) -> None:
        try:
            logger = self.monkey.log
            logger.info("Starting up...")
            self._client = JupyterClient(
                self.monkey.user, logger, self.options
            )
            self.start_event("pre_login_delay")
            await asyncio.sleep(random.uniform(0, 30))
            self.stop_current_event()
            self.start_event("hub_login")
            await self._client.hub_login()
            self.stop_current_event()
            await asyncio.sleep(random.uniform(10, 30))
            while True:
                logger.info("Starting next iteration")
                self.start_event("ensure_lab")
                await self._client.ensure_lab()
                self.stop_current_event()
                logger.info("Lab created.")
                self.start_event("lab_wait")
                # await asyncio.sleep(30 + random.uniform(0, 60))
                await asyncio.sleep(1200 + random.uniform(0, 600))
                self.stop_current_event()
                logger.info("Deleting lab.")
                self.start_event("delete_lab")
                await self._client.delete_lab()
                self.stop_current_event()
                self.success_count += 1
                logger.info("Lab successfully deleted.")
                self.start_event("no_lab_wait")
                await asyncio.sleep(30 + random.uniform(0, 60))
                self.stop_current_event()
        except Exception:
            self.failure_count += 1
            raise

    def dump(self) -> dict:
        r = super().dump()
        r.update(
            {
                "name": "JupyterJitterLoginLoop",
            }
        )
        return r
