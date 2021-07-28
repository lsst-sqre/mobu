"""JupyterJitterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new JupyterLab instances on a
nublado instance, with jitter built in to the timing, and then delete those
instances.
"""

from __future__ import annotations

import random

from .jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterJitterLoginLoop"]


class JupyterJitterLoginLoop(JupyterLoginLoop):
    """A variation of JupyterLoginLoop that adds some random delays."""

    async def startup(self) -> None:
        with self.timings.start("pre_login_delay"):
            await self.pause(random.uniform(0, 30))
        if self.stopping:
            return
        await super().startup()
        await self.pause(random.uniform(10, 30))

    async def lab_business(self) -> None:
        with self.timings.start("lab_wait"):
            await self.pause(1200 + random.uniform(0, 600))

    async def idle(self) -> None:
        self.logger.info("Idling...")
        with self.timings.start("idle"):
            await self.pause(30 + random.uniform(0, 60))
