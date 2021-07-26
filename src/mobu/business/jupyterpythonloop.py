"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

import asyncio

from ..jupyterclient import JupyterLabSession
from .jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterPythonLoop"]

MAX_EXECUTIONS = 20
SLEEP_TIME = 1


class JupyterPythonLoop(JupyterLoginLoop):
    """Run simple Python code in a loop inside a lab kernel."""

    async def lab_business(self) -> None:
        session = await self.create_session()
        for count in range(MAX_EXECUTIONS):
            await self.execute_code(session, "2+2")
            await self.lab_wait()
        await self.delete_session(session)

    async def create_session(self) -> JupyterLabSession:
        self.logger.info("create_session")
        with self.timings.start("create_session"):
            session = await self._client.create_labsession()
        return session

    async def execute_code(
        self, session: JupyterLabSession, code: str
    ) -> None:
        with self.timings.start("execute_code", {"code": code}) as sw:
            reply = await self._client.run_python(session, code)
            sw.annotation["result"] = reply
        self.logger.info(f"{code} -> {reply}")

    async def lab_wait(self) -> None:
        with self.timings.start("lab_wait"):
            await asyncio.sleep(SLEEP_TIME)

    async def delete_session(self, session: JupyterLabSession) -> None:
        self.logger.info("delete_session")
        with self.timings.start("delete_session"):
            await self._client.delete_labsession(session)
