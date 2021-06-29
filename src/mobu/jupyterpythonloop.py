"""JupyterPythonLoop logic for mobu.

This business pattern will start jupyter and run some code
in a loop over and over again."""

__all__ = [
    "JupyterPythonLoop",
]

import asyncio
from dataclasses import dataclass

from mobu.jupyterclient import JupyterClient
from mobu.jupyterloginloop import JupyterLoginLoop


@dataclass
class JupyterPythonLoop(JupyterLoginLoop):
    async def run(self) -> None:
        logger = self.monkey.log
        logger.info("Starting up...")

        client = JupyterClient(self.monkey.user, logger, self.options)
        self._client = client
        self.start_event("hub_login")
        await self._client.hub_login()
        self.stop_current_event()
        self.start_event("ensure_lab")
        await client.ensure_lab()
        self.stop_current_event()
        self.start_event("create_kernel")
        kernel = await client.create_kernel()
        self.stop_current_event()

        while True:
            self.start_event("execute_code")
            code_str = "print(2+2)"
            reply = await client.run_python(kernel, code_str)
            sw = self.get_current_event()
            if sw is not None:
                sw.annotation = {"code": code_str, "result": reply}
            self.stop_current_event()
            logger.info(f"{code_str} -> {reply}")
            self.start_event("lab_wait")
            await asyncio.sleep(60)
            self.stop_current_event()

    def dump(self) -> dict:
        r = super().dump()
        r.update({"name": "JupyterPythonLoop"})
        return r
