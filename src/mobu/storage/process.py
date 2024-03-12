"""Class with method to execute noninteractive subprocesses asynchronously."""

import asyncio
from pathlib import Path
from shlex import join

from structlog.stdlib import BoundLogger

from ..exceptions import AsyncioProcessError
from ..models.user import AuthenticatedUser


class Process:
    """A thin wrapper around asyncio.subprocess.create_process_exec."""

    def __init__(
        self,
        *,
        user: AuthenticatedUser | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        self._user = user
        self._logger = logger

    async def exec(
        self,
        cmd: str,
        *args: str,
        cwd: Path | None = None,
    ) -> asyncio.subprocess.Process:
        l_args = [cmd]
        l_args.extend(args)
        msg = join(l_args)

        username = self._user.username if self._user else "nobody"

        proc = await asyncio.subprocess.create_subprocess_exec(
            cmd,
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()  # Waits for process exit

        msg += f" exited with rc={proc.returncode}"  # which should be 0
        if proc.stdout is not None:
            msg += f'; stdout="{stdout.decode()}"'
        if proc.stderr is not None:
            msg += f'; stderr="{stderr.decode()}"'
        if proc.returncode != 0:
            raise AsyncioProcessError(msg, user=username)

        if self._logger:
            self._logger.debug(msg)
        return proc
