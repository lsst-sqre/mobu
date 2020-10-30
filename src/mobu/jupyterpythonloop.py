"""JupyterPythonLoop logic for mobu.

This business pattern will start jupyter and run some code
in a loop over and over again."""

__all__ = [
    "JupyterPythonLoop",
]

import asyncio
from dataclasses import dataclass

from mobu.business import Business
from mobu.jupyterclient import JupyterClient


@dataclass
class JupyterPythonLoop(Business):
    async def run(self) -> None:
        logger = self.monkey.log
        logger.info("Starting up...")

        client = JupyterClient(self.monkey.user, logger, self.options)
        await client.hub_login()
        await client.ensure_lab()

        kernel = await client.create_kernel()

        while True:
            reply = await client.run_python(kernel, "print(2+2)")
            logger.info(reply)
            await asyncio.sleep(60)

    def dump(self) -> dict:
        return {"name": "JupyterPythonLoop"}
