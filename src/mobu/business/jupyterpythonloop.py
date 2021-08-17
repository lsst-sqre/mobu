"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..jupyterclient import JupyterLabSession
from .jupyterloginloop import JupyterLoginLoop

if TYPE_CHECKING:
    from typing import Optional

    from structlog import BoundLogger

    from ..models.business import BusinessConfig
    from ..user import AuthenticatedUser

__all__ = ["JupyterPythonLoop"]

_CHDIR_TEMPLATE = 'import os; os.chdir("{wd}")'
"""Template to construct the code to run to set the working directory."""

_GET_NODE = """
from rubin_jupyter_utils.lab.notebook.utils import get_node
import warnings
warnings.filterwarnings("ignore")
print(get_node(), end="")
"""
"""Code to get the node on which the lab is running."""


class JupyterPythonLoop(JupyterLoginLoop):
    """Run simple Python code in a loop inside a lab kernel.

    This can be used as a base class for other JupyterLab code execution
    monkey business.  Override ``execute_code`` to change what code is
    executed.  When doing so, be sure to call ``execute_idle`` between each
    code execution and check ``self.stopping`` after it returns, exiting any
    loops if ``self.stopping`` is true.
    """

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        self.node: Optional[str] = None

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
        with self.timings.start("execute_setup"):
            if self.config.get_node:
                self.node = await self._client.run_python(session, _GET_NODE)
            if self.config.working_directory:
                code = _CHDIR_TEMPLATE.format(wd=self.config.working_directory)
                await self._client.run_python(session, code)
        return session

    async def execute_code(self, session: JupyterLabSession) -> None:
        code = self.config.code
        for count in range(self.config.max_executions):
            with self.timings.start("execute_code", {"node": self.node}):
                reply = await self._client.run_python(session, code)
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
