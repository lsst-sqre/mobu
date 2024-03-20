"""A very simple async replacement for GitPython.

GitPython is not thread- or async-safe because of a git quirk: current
working directory is a per-process global, and "git add" requires that
the cwd be inside a worktree.
"""

import asyncio
import os
from pathlib import Path
from shlex import join

from structlog.stdlib import BoundLogger

from ..exceptions import SubprocessError


class Git:
    """A very basic async Git client based on asyncio.subprocess.

    Parameters
    ----------
    repo
        Filesystem path for the git repository.
    config_location
        Filesystem path for the file to use as the user-global Git config.
    logger
        Logger to use.
    """

    def __init__(
        self,
        *,
        repo: Path | None = None,
        config_location: Path | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        self.repo = repo
        self._logger = logger
        self._config_location = config_location

    async def _exec(
        self,
        cmd: str,
        *args: str,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        """Execute a non-interactive subprocess.

        We need this to make the git commands behave correctly in an
        async environment.  The reason why is a little subtle.  Most git
        commands let you specify arbitrary paths, but not `git add`.  To
        run a git add, you have to have a working tree, and that means that
        the current working directory has to be inside that working tree.

        The current working directory is a per-process global.  So if we
        didn't do this, then mobu, which may be running many tests at once
        in different coroutines, will get very confused.

        However, since we're creating a subprocess to run the git
        executable anyway, we can run it with asyncio.subprocess,
        optionally with the working directory set to an arbitrary
        path.  That way, mobu's working directory stays untouched, but
        the subprocess may execute somewhere else.

        The environment will be sent to a Slack message on failure, and logged
        if debugging is turned on, so it's important not to put any secrets
        into it.
        """
        l_args = [cmd]
        l_args.extend(args)
        cmd_and_args = join(l_args)

        proc = await asyncio.subprocess.create_subprocess_exec(
            cmd,
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()  # Waits for process exit

        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""
        if proc.returncode != 0:
            raise SubprocessError(
                f"Subprocess '{cmd_and_args}' failed",
                returncode=proc.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                cwd=cwd,
                env=env,
            )
        if self._logger:
            self._logger.debug(
                f"'{cmd_and_args}' exited",
                returncode=proc.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                cwd=str(cwd),
                env=env,
            )

    async def git(self, *args: str) -> None:
        """Run an arbitrary git command with arbitrary string arguments.

        Constrain the environment of the subprocess: only pass HOME, LANG,
        PATH, and any GIT_ variables.

        If self.repo is set, use that as the working directory.  If
        self._config_location is set, use that as the value of
        GIT_CONFIG_GLOBAL, and set GIT_CONFIG_SYSTEM to the empty string.

        This is intended to constrain where git looks for its definitions,
        making it both function in mobu business and not break developers'
        git setups.
        """
        env = {
            "PATH": os.environ.get("PATH", "/bin:/usr/bin"),
            "HOME": os.environ.get("HOME", "/"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        for var in os.environ:
            if var.startswith("GIT_"):
                env[var] = os.environ[var]
        if self._config_location:
            env["GIT_CONFIG_GLOBAL"] = str(self._config_location)
            env["GIT_CONFIG_SYSTEM"] = ""

        await self._exec("git", *args, cwd=self.repo, env=env)

    async def init(self, *args: str) -> None:
        """Run `git init` with arbitrary arguments.

        If self.repo is None, and this is run, it will set self.repo
        from the last argument as a side effect.  If there are no
        arguments, self.repo becomes the current working directory.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("init", *args)
        if self.repo is None:
            if len(args) == 0:
                self.repo = Path()
            else:
                self.repo = Path(args[-1])

    async def add(self, *args: str) -> None:
        """Run `git add` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("add", *args)

    async def commit(self, *args: str) -> None:
        """Run `git commit` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("commit", *args)

    async def push(self, *args: str) -> None:
        """Run `git commit` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("push", *args)

    async def config(self, *args: str) -> None:
        """Run `git config` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("config", *args)

    async def pull(self, *args: str) -> None:
        """Run `git pull` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("pull", *args)

    async def fetch(self, *args: str) -> None:
        """Run `git fetch` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("fetch", *args)

    async def branch(self, *args: str) -> None:
        """Run `git branch` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("branch", *args)

    async def clone(self, *args: str) -> None:
        """Run `git clone` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("clone", *args)

    async def lfs(self, *args: str) -> None:
        """Run `git lfs` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("lfs", *args)

    async def checkout(self, *args: str) -> None:
        """Run `git checkout` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("checkout", *args)

    async def reset(self, *args: str) -> None:
        """Run `git reset` with arbitrary arguments.

        Parameters
        ----------
        *args
            Arguments to command.
        """
        await self.git("reset", *args)
