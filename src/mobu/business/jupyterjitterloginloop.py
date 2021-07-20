"""JupyterJitterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new JupyterLab instances on a
nublado instance, with jitter built in to the timing, and then delete those
instances.
"""

from __future__ import annotations

import asyncio
import random

from .jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterJitterLoginLoop"]


class JupyterJitterLoginLoop(JupyterLoginLoop):
    """A variation of JupyterLoginLoop that adds some random delays."""

    async def startup(self) -> None:
        self.start_event("pre_login_delay")
        await asyncio.sleep(random.uniform(0, 30))
        self.stop_current_event()
        await super().startup()
        await asyncio.sleep(random.uniform(10, 30))

    async def lab_business(self) -> None:
        self.start_event("lab_wait")
        await asyncio.sleep(1200 + random.uniform(0, 600))
        self.stop_current_event()

    async def idle(self) -> None:
        self.start_event("no_lab_wait")
        await asyncio.sleep(30 + random.uniform(0, 60))
        self.stop_current_event()
