"""JupyterPythonLoop logic for mobu.

This business pattern will start a lab and run some code in a loop over and
over again.
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from structlog.stdlib import BoundLogger

from ...models.business.jupyterpythonloop import (
    JupyterPythonExecutorOptions,
    JupyterPythonLoopOptions,
)
from ...models.user import AuthenticatedUser
from ...storage.jupyter import JupyterLabSession
from .jupyterloginloop import JupyterLoginLoop

T = TypeVar("T", bound="JupyterPythonExecutorOptions")

__all__ = ["JupyterPythonLoop"]

_CHDIR_TEMPLATE = 'import os; os.chdir("{wd}")'
"""Template to construct the code to run to set the working directory."""

_GET_NODE = """
from rubin_jupyter_utils.lab.notebook.utils import get_node
print(get_node(), end="")
"""
"""Code to get the node on which the lab is running."""


class JupyterPythonLoop(JupyterLoginLoop, Generic[T]):
    """Run simple Python code in a loop inside a lab kernel.

    This can be used as a base class for other JupyterLab code execution
    monkey business. Override `execute_code` to change what code is
    executed. When doing so, be sure to call `execution_idle` between each
    code execution and exit any loops if it returns `False`.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self, options: T, user: AuthenticatedUser, logger: BoundLogger
    ) -> None:
        super().__init__(options, user, logger)
        self.node: Optional[str] = None

    def annotations(self) -> dict[str, str]:
        result = super().annotations()
        if self.node:
            result["node"] = self.node
        return result

    async def lab_business(self) -> None:
        if self.stopping:
            return
        session = await self.create_session()
        await self.execute_code(session)
        await self.delete_session(session)

    async def create_session(
        self, notebook_name: Optional[str] = None
    ) -> JupyterLabSession:
        self.logger.info("Creating lab session")
        with self.timings.start("create_session", self.annotations()):
            session = await self._client.create_labsession(notebook_name)
        with self.timings.start("execute_setup", self.annotations()):
            if self.config.get_node:
                # Our libraries currently spew warning messages when imported.
                # The node is only the last line of the output.
                node_data = await self._client.run_python(session, _GET_NODE)
                self.node = node_data.split("\n")[-1]
                self.logger.info(f"Running on node {self.node}")
            if self.config.working_directory:
                path = self.config.working_directory
                code = _CHDIR_TEMPLATE.format(wd=path)
                self.logger.info(f"Changing directories to {path}")
                await self._client.run_python(session, code)
        return session

    async def execute_code(self, session: JupyterLabSession) -> None:
        if not isinstance(self.config, JupyterPythonLoopOptions):
            msg = "JupyterPythonLoop subclass didn't override execute_code"
            raise RuntimeError(msg)
        code = self.config.code
        for count in range(self.config.max_executions):
            with self.timings.start("execute_code", self.annotations()):
                reply = await self._client.run_python(session, code)
            self.logger.info(f"{code} -> {reply}")
            if not await self.execution_idle():
                break

    async def execution_idle(self) -> bool:
        """Executed between each unit of work execution."""
        with self.timings.start("execution_idle"):
            return await self.pause(self.config.execution_idle_time)

    async def delete_session(self, session: JupyterLabSession) -> None:
        await self.lab_login()
        self.logger.info("Deleting lab session")
        with self.timings.start("delete_session", self.annotations()):
            await self._client.delete_labsession(session)
        self.node = None
