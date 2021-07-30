"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from ..jupyterclient import JupyterLabSession
from .jupyterloginloop import JupyterLoginLoop

__all__ = ["JupyterPythonLoop"]


class JupyterPythonLoop(JupyterLoginLoop):
    """Run simple Python code in a loop inside a lab kernel.

    This can be used as a base class for other JupyterLab code execution
    monkey business.  Override ``execute_code`` to change what code is
    executed.  When doing so, be sure to call ``execute_idle`` between each
    code execution and check ``self.stopping`` after it returns, exiting any
    loops if ``self.stopping`` is true.
    """

    async def lab_business(self) -> None:
        if self.stopping:
            return
        session = await self.create_session()
        await self.execute_code(session)
        await self.delete_session(session)

    async def create_session(self) -> JupyterLabSession:
        self.logger.info("Creating lab session")
        with self.timings.start("create_session"):
            session = await self._client.create_labsession()
        return session

    async def execute_code(self, session: JupyterLabSession) -> None:
        code = self.config.code
        for count in range(self.config.max_executions):
            with self.timings.start("execute_code", {"code": code}) as sw:
                reply = await self._client.run_python(session, code)
                sw.annotation["result"] = reply
            self.logger.info(f"{code} -> {reply}")
            await self.execution_idle()
            if self.stopping:
                break

    async def execution_idle(self) -> None:
        """Executed between each unit of work execution."""
        with self.timings.start("execution_idle"):
            await self.pause(self.config.execution_idle_time)

    async def delete_session(self, session: JupyterLabSession) -> None:
        await self.lab_login()
        self.logger.info("Deleting lab session")
        with self.timings.start("delete_session"):
            await self._client.delete_labsession(session)
