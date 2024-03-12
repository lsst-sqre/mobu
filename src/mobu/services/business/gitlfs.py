"""Class for executing Git-LFS tests."""

import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...exceptions import GitError
from ...models.business.gitlfs import GitLFSBusinessOptions
from ...models.user import AuthenticatedUser
from ...storage.git import Git
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
        self._skip_lfs = options.skip_lfs
        self._git = Git(user=user, logger=logger)

    async def execute(self) -> None:
        self.logger.info("Running Git-LFS check:")
        with self.timings.start("execute git-lfs check") as sw:
            try:
                await self._git_lfs_check()
            except Exception as e:
                raise GitError(e, user=self.user.username) from e
            elapsed = sw.elapsed.total_seconds()
        self.logger.info(f"Git-LFS check finished after {elapsed} seconds")

    async def _git_lfs_check(self) -> None:
        repo_uuid = uuid.uuid4()
        readme_text = (
            "# Git-LFS test repo\nTest repository for Git-LFS checking\n"
        )
        with tempfile.TemporaryDirectory() as working_dir:
            # Create the upstream repository.
            working_path = Path(working_dir)
            with self.timings.start("init upstream repo"):
                origin_path = Path(working_path / "origin")
                origin_path.mkdir()
                self._git.set_repo(origin_path)
                await self._git.init("--bare", "-b", "main", str(origin_path))

            # Create the source repository we're going to push upstream
            repo_path = Path(working_path / "repo")
            repo_path.mkdir()
            with self.timings.start("write data into checkout repo"):
                await self._initialize_repo_contents(
                    origin_path, repo_path, repo_uuid, readme_text
                )
            with self.timings.start("commit/push checkout repo"):
                await self._commit_and_push_repo(repo_path)

            clone_path = Path(working_path / "clone")
            clone_path.mkdir()
            with self.timings.start("clone upstream repo"):
                self._git.set_repo(clone_path)
                await self._git.clone(
                    str(origin_path), "-b", "main", str(clone_path)
                )
            with self.timings.start("check cloned repo contents"):
                await self._check_repo_contents(
                    clone_path, repo_uuid, readme_text
                )

    async def _initialize_repo_contents(
        self,
        upstream_path: Path,
        repo_path: Path,
        repo_uuid: uuid.UUID,
        readme_text: str,
    ) -> None:
        here = Path(repo_path)
        self._git.set_repo(repo_path)
        await self._git.clone(str(upstream_path), str(repo_path))

        # Create repo files
        Path(here / "README.md").write_text(readme_text)
        if not self._skip_lfs:  # Only EVER skip LFS for unit testing.
            with self.timings.start("write LFS configuration"):
                await self._git.lfs("install", "--local")
                Path(here / ".gitattributes").write_text(
                    "assets/* filter=lfs diff=lfs merge=lfs -text\n"
                )
                Path(here / ".lfsconfig").write_text(
                    f"[lfs]\n        url = {self._lfs_read_url}\n"
                )
        asset_dir = Path(here / "assets")
        asset_dir.mkdir()
        Path(asset_dir / "UUID").write_text(repo_uuid.hex)

    async def _commit_and_push_repo(self, repo: Path) -> None:
        self._git.set_repo(repo)
        await self._git.config("user.email", "gituser@example.com")
        await self._git.config("user.name", "Git User")
        await self._git.checkout("-b", "main")
        await self._git.add("README.md")
        if not self._skip_lfs:  # Only EVER skip LFS for unit testing.
            with self.timings.start("add LFS configuration to commit"):
                await self._git.config(
                    "--local", "lfs.url", self._lfs_write_url
                )
                await self._git.config("--local", "lfs.locksverify", "false")
                await self._git.config(
                    "--local", "lfs.repositoryformatversion", "0"
                )
                await self._git.config("--local", "lfs.access", "basic")
                await self._git.add(".gitattributes")
                await self._git.add(".lfsconfig")
        await self._git.add("assets/UUID")
        await self._git.commit("-m", "Initial Commit")
        if not self._skip_lfs:  # Add the git credentials last thing
            with self.timings.start("add git credentials"):
                credfile = Path(repo.parent / ".git_credentials")
                credfile.touch()
                credfile.chmod(0o700)
                w_url = urlparse(self._lfs_write_url)
                await self._git.config(
                    "--local",
                    f"credential.{w_url.scheme}://{w_url.netloc}.helper",
                    f"store --file {credfile!s}",
                )
                creds = (
                    f"{w_url.scheme}://gituser:"
                    f"{self.user.token}@{w_url.netloc}"
                )
                credfile.write_text(creds)
        with self.timings.start("git push"):
            await self._git.push("--set-upstream", "origin", "main")
        if not self._skip_lfs:  # Remove git credentials
            with self.timings.start("remove git credentials"):
                credfile.unlink()

    async def _check_repo_contents(
        self, clone_path: Path, repo_uuid: uuid.UUID, readme_text: str
    ) -> None:
        read_text = Path(clone_path / "README.md").read_text()
        if read_text != readme_text:
            raise ValueError(
                f'Expected text: "{readme_text}"\n' f'Got text: "{read_text}"'
            )
        read_uuid = Path(clone_path / "assets" / "UUID").read_text()
        if read_uuid != repo_uuid.hex:
            raise ValueError(
                f'Expected UUID "{repo_uuid.hex}; ' f'Got UUID "{read_uuid}"'
            )
