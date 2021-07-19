"""JupyterJitterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new JupyterLab
instances on a nublado instance, with jitter built in to the timing,
and then delete those instances."""

from __future__ import annotations

import asyncio
import random

from mobu.business.jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterJitterLoginLoop"]


class JupyterJitterLoginLoop(JupyterLoginLoop):
    async def run(self) -> None:
        try:
            self.logger.info("Starting up...")
            self.start_event("pre_login_delay")
            await asyncio.sleep(random.uniform(0, 30))
            self.stop_current_event()
            self.start_event("hub_login")
            await self._client.hub_login()
            self.stop_current_event()
            await asyncio.sleep(random.uniform(10, 30))
            while True:
                self.logger.info("Starting next iteration")
                self.start_event("ensure_lab")
                await self._client.ensure_lab()
                self.stop_current_event()
                self.logger.info("Lab created.")
                self.start_event("lab_wait")
                # await asyncio.sleep(30 + random.uniform(0, 60))
                await asyncio.sleep(1200 + random.uniform(0, 600))
                self.stop_current_event()
                self.logger.info("Deleting lab.")
                self.start_event("delete_lab")
                await self._client.delete_lab()
                self.stop_current_event()
                self.success_count += 1
                self.logger.info("Lab successfully deleted.")
                self.start_event("no_lab_wait")
                await asyncio.sleep(30 + random.uniform(0, 60))
                self.stop_current_event()
        except Exception:
            self.failure_count += 1
            raise
