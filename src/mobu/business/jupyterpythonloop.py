"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

import asyncio
from dataclasses import dataclass

from mobu.business.jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterPythonLoop"]

MAX_EXECUTIONS = 20
SLEEP_TIME = 1


@dataclass
class JupyterPythonLoop(JupyterLoginLoop):
    """Run simple Python code in a loop inside a lab kernel."""

    async def lab_business(self) -> None:
        kernel = await self.create_kernel()
        for count in range(MAX_EXECUTIONS):
            await self.execute_code(kernel, "2+2")
            await self.lab_wait()
        await self.delete_kernel(kernel)

    async def create_kernel(self) -> str:
        self.logger.info("create_kernel")
        self.start_event("create_kernel")
        kernel = await self._client.create_kernel()
        self.stop_current_event()
        return kernel

    async def execute_code(self, kernel: str, code: str) -> None:
        self.start_event("execute_code")
        reply = await self._client.run_python(kernel, code)
        sw = self.get_current_event()
        if sw is not None:
            sw.annotation = {"code": code, "result": reply}
        self.stop_current_event()
        self.logger.info(f"{code} -> {reply}")

    async def lab_wait(self) -> None:
        self.start_event("lab_wait")
        await asyncio.sleep(SLEEP_TIME)
        self.stop_current_event()

    async def delete_kernel(self, kernel: str) -> None:
        self.logger.info("delete_kernel")
        self.start_event("delete_kernel")
        await self._client.delete_kernel(kernel)
        self.stop_current_event()
