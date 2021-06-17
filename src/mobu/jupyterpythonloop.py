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
from mobu.timing import CodeTimingData, PythonTimingData, TimeInfo


@dataclass
class JupyterPythonLoop(JupyterLoginLoop):
    async def run(self) -> None:
        logger = self.monkey.log
        logger.info("Starting up...")

        client = JupyterClient(self.monkey.user, logger, self.options)
        self._client = client
        stamp = PythonTimingData(start=TimeInfo.stamp(previous=None))
        self.timings.append(stamp)
        await self._client.hub_login()
        stamp.login_complete = TimeInfo.stamp(previous=stamp.start)
        await client.ensure_lab()
        stamp.lab_created = TimeInfo.stamp(previous=stamp.login_complete)
        kernel = await client.create_kernel()
        stamp.kernel_created = TimeInfo.stamp(previous=stamp.lab_created)

        while True:
            runstamp = CodeTimingData(start=TimeInfo.stamp())
            code_str = "print(2+2)"
            runstamp.code = code_str
            stamp.code.append(runstamp)
            reply = await client.run_python(kernel, code_str)
            runstamp.stop = TimeInfo.stamp(previous=runstamp.start)
            logger.info(reply)
            # Don't time the sleep
            await asyncio.sleep(60)

    async def stop(self) -> None:
        await self._client.delete_lab()

    def dump(self) -> dict:
        r = super().dump()
        r.update({"name": "JupyterPythonLoop"})
        return r
