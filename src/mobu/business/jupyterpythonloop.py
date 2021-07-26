"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

import asyncio

from .jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterPythonLoop"]

MAX_EXECUTIONS = 20
SLEEP_TIME = 1


class JupyterPythonLoop(JupyterLoginLoop):
    """Run simple Python code in a loop inside a lab kernel."""

    async def lab_business(self) -> None:
        kernel = await self.create_kernel()
        for count in range(MAX_EXECUTIONS):
            await self.execute_code(kernel, "print(2+2, end='')")
            await self.lab_wait()
        await self.delete_kernel(kernel)

    async def create_kernel(self) -> str:
        self.logger.info("create_kernel")
        with self.timings.start("create_kernel"):
            kernel = await self._client.create_kernel()
        return kernel

    async def execute_code(self, kernel: str, code: str) -> None:
        with self.timings.start("execute_code", {"code": code}) as sw:
            reply = await self._client.run_python(kernel, code)
            sw.annotation["result"] = reply
        self.logger.info(f"{code} -> {reply}")

    async def lab_wait(self) -> None:
        with self.timings.start("lab_wait"):
            await asyncio.sleep(SLEEP_TIME)

    async def delete_kernel(self, kernel: str) -> None:
        self.logger.info("delete_kernel")
        with self.timings.start("delete_kernel"):
            await self._client.delete_kernel(kernel)
