"""Class for executing Git-LFS tests."""

import asyncio
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from git.repo import Repo
from git.util import Actor
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...exceptions import GitLFSError
from ...models.business.gitlfs import GitLFSBusinessOptions
from ...models.user import AuthenticatedUser
from .base import Business


class GitLFSBusiness(Business):
    """Check out a Git-LFS backed repository, edit a Git-LFS-backed asset,
    and push it back.
    """

    def __init__(
        self,
        options: GitLFSBusinessOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._lfs_read_url = options.lfs_read_url
        self._lfs_write_url = options.lfs_write_url
        self._pool = ThreadPoolExecutor(max_workers=1)

    async def execute(self) -> None:
        with self.timings.start("execute git-lfs check") as sw:
            try:
                await self.run_gitlfs_check()
            except Exception as e:
                raise GitLFSError(e, user=self.user.username) from e
            elapsed = sw.elapsed.total_seconds()
        self.logger.info(f"Query finished after {elapsed} seconds")

    async def run_gitlfs_check(self) -> None:
        """Run a Git LFS transaction."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._pool, self._git_lfs_check)

    def _git_lfs_check(self) -> None:
        repo_uuid = uuid.uuid4()
        readme_text = (
            "# Git-LFS test repo\nTest repository for Git-LFS checking\n"
        )
        with tempfile.TemporaryDirectory() as upstream_path:
            # Create the upstream repository.
            with self.timings.start("init upstream repo"):
                upstream_repo = Repo.init(
                    upstream_path, bare=True, initial_branch="main"
                )

            # Create the source repository we're going to push upstream
            with tempfile.TemporaryDirectory() as repo_path:
                with self.timings.start("init checkout repo"):
                    self._initialize_repo_contents(
                        repo_path, repo_uuid, readme_text
                    )
                with self.timings.start("commit/push checkout repo"):
                    self._commit_and_push_repo(repo_path, upstream_path)

            # Now the initial repo is gone; let's clone upstream
            # and then check whether both the regular file and the Git-LFS
            # backed file are correct

            with tempfile.TemporaryDirectory() as clone_path:
                with self.timings.start("clone upstream repo"):
                    upstream_repo.clone(clone_path)
                with self.timings.start("check cloned contents"):
                    self._check_repo_contents(
                        clone_path, repo_uuid, readme_text
                    )

    def _initialize_repo_contents(
        self, repo_path: str, repo_uuid: uuid.UUID, readme_text: str
    ) -> None:
        here = Path(repo_path)

        with Path(here / "README.md").open("w") as f:
            f.write(readme_text)

        with Path(here / ".gitattributes").open("w") as f:
            f.write("assets/* filter=lfs diff=lfs merge=lfs -text\n")

        with Path(here / ".lfsconfig").open("w") as f:
            f.write(f"[lfs]\n        url = {self._lfs_read_url}\n")

        asset_dir = Path(here / "assets")
        asset_dir.mkdir()
        with Path(asset_dir / "UUID").open("w") as f:
            f.write(repo_uuid.hex)

    def _commit_and_push_repo(
        self, repo_path: str, upstream_path: str
    ) -> None:
        # All the repo functions work on str, not Path
        repo = Repo.init(repo_path, initial_branch="main")
        actor = Actor("Frank Booth", "bluevelvet@example.com")
        with repo.config_writer() as cfg:
            cfg.set_value("lfs", "url", self._lfs_write_url)
            cfg.set_value("lfs", "locksverify", "false")
        repo.index.add("README.md")
        repo.index.add(".gitattributes")
        repo.index.add(".lfsconfig")
        repo.index.add("assets/UUID")
        repo.index.commit("Initial commit", author=actor, committer=actor)
        origin = repo.create_remote("origin", upstream_path)
        origin.push(all=True)

    def _check_repo_contents(
        self, clone_path: str, repo_uuid: uuid.UUID, readme_text: str
    ) -> None:
        here = Path(clone_path)
        with Path(here / "README.md").open() as f:
            read_text = f.read()
            if read_text != readme_text:
                raise ValueError(
                    f'Expected text: "{readme_text}"\n'
                    f'Got text: "{read_text}"'
                )
        with Path(here / "assets" / "UUID").open() as f:
            read_uuid = f.read()
            if read_uuid != repo_uuid.hex:
                raise ValueError(
                    f'Expected UUID "{repo_uuid.hex}; '
                    f'Got UUID "{read_uuid}"'
                )
