"""A very simple async replacement for GitPython, which has been
abandoned and is distinctly not thread- or async-safe.
"""

from pathlib import Path

from structlog.stdlib import BoundLogger

from ..models.user import AuthenticatedUser
from .process import Process


class Git:
    """A very basic async Git client based on asyncio.subprocess."""

    def __init__(
        self,
        *,
        repo: Path | None = None,
        user: AuthenticatedUser | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        self._user = user
        if self._user is None:
            self._user = AuthenticatedUser(
                username="gituser",
                uidnumber=60001,
                gidnumber=60001,
                scopes=[],
                token="dummy token",
            )
        self._logger = logger
        self._repo = repo
        self._process = Process(user=self._user, logger=self._logger)

    def set_repo(self, repo: Path) -> None:
        self._repo = repo

    async def git(self, *args: str) -> None:
        await self._process.exec("git", *args, cwd=self._repo)

    async def init(self, *args: str) -> None:
        await self.git("init", *args)

    async def add(self, *args: str) -> None:
        await self.git("add", *args)

    async def commit(self, *args: str) -> None:
        await self.git("commit", *args)

    async def push(self, *args: str) -> None:
        await self.git("push", *args)

    async def config(self, *args: str) -> None:
        await self.git("config", *args)

    async def pull(self, *args: str) -> None:
        await self.git("pull", *args)

    async def fetch(self, *args: str) -> None:
        await self.git("fetch", *args)

    async def branch(self, *args: str) -> None:
        await self.git("branch", *args)

    async def clone(self, *args: str) -> None:
        await self.git("clone", *args)

    async def lfs(self, *args: str) -> None:
        await self.git("lfs", *args)

    async def checkout(self, *args: str) -> None:
        await self.git("checkout", *args)
