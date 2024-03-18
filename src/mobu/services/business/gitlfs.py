"""Class for executing Git-LFS tests."""

import importlib
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...exceptions import ComparisonError
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
        self._package_data = Path(
            Path(str(importlib.resources.files("mobu").joinpath("data")))
            / "gitlfs"
        )
        # This saves us a lot of convincing mypy that it's not None; reads
        # or writes will of course fail if it's not changed.
        self._working_dir = Path("/nonexistent")
        # Likewise, any UUID checks will fail if it's not updated
        self._uuid = "this is not a valid UUID"

    async def execute(self) -> None:
        self.logger.info("Running Git-LFS check...")
        with self.timings.start("execute git-lfs check") as sw:
            await self._git_lfs_check()
        elapsed = sw.elapsed.total_seconds()
        self.logger.info(f"...Git-LFS check finished after {elapsed}s")

    def _git(self, repo: Path) -> Git:
        """Return a configured Git client for a specified repo path.

        This will use the packaged gitconfig unless config_location is
        specified.
        """
        return Git(
            config_location=Path(self._package_data / "gitconfig"),
            repo=repo,
            logger=self.logger,
        )

    async def _git_lfs_check(self) -> None:
        self._uuid = uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as working_dir:
            self._working_dir = Path(working_dir)
            with self.timings.start("create origin repo"):
                await self._create_origin_repo()
            with self.timings.start("populate origin repo"):
                await self._populate_origin_repo()
            with self.timings.start("create checkout repo"):
                await self._create_checkout_repo()
            with self.timings.start("add LFS-tracked assets"):
                await self._add_lfs_assets()
            git = self._git(repo=Path(self._working_dir / "checkout"))
            with self.timings.start("add git credentials"):
                await self._add_credentials(git)
            with self.timings.start("push LFS-tracked assets"):
                await git.push("origin", "main")
            with self.timings.start("remove git credentials"):
                Path(self._working_dir / ".git_credentials").unlink()
            with self.timings.start("verify origin contents"):
                await self._verify_origin_contents()
            with self.timings.start("create clone repo with asset"):
                await self._create_clone_repo()
            with self.timings.start("verify asset contents"):
                await self._verify_asset_contents()

    async def _create_origin_repo(self) -> None:
        origin = Path(self._working_dir / "origin")
        origin.mkdir()
        git = self._git(repo=origin)
        await git.init("--initial-branch=main", str(origin))

    async def _create_checkout_repo(self) -> None:
        origin = Path(self._working_dir / "origin")
        checkout = Path(self._working_dir / "checkout")
        checkout.mkdir()
        git = self._git(repo=checkout)
        await git.clone(str(origin), str(checkout))

    async def _create_clone_repo(self) -> None:
        clone_path = Path(self._working_dir / "clone")
        clone_path.mkdir()
        # We don't want to use the standard global git config, because we
        # want to install LFS (and thus get the right filters) *before* we
        # clone the repository.  So we'll create our own git config that
        # we can write, install git LFS into it, and then clone.
        with tempfile.NamedTemporaryFile() as gcfile:
            gitconfig = Path(gcfile.name)
            shutil.copyfile((self._package_data / "gitconfig"), gitconfig)
            git = Git(
                repo=clone_path, logger=self.logger, config_location=gitconfig
            )
            await self._install_git_lfs(git, "")
            await git.clone(
                str(Path(self._working_dir / "origin")),
                "-b",
                "main",
                str(clone_path),
            )
            await git.pull()

    async def _populate_origin_repo(self) -> None:
        srcdir = self._package_data
        origin = Path(self._working_dir / "origin")
        shutil.copyfile((srcdir / "README.md"), (origin / "README.md"))
        Path(origin / ".lfsconfig").write_text(
            f"[lfs]\n        url = {self._lfs_read_url}\n"
        )
        git = self._git(repo=origin)
        await git.add("README.md")
        await git.add(".lfsconfig")
        await git.commit("-am", "Initial commit")

    async def _add_lfs_assets(self) -> None:
        checkout_path = Path(self._working_dir / "checkout")
        git = self._git(repo=checkout_path)
        with self.timings.start("install git lfs to checkout repo"):
            await self._install_git_lfs(git)
        with self.timings.start("add lfs data to checkout repo"):
            await self._add_git_lfs_data(git)
        asset_path = Path(checkout_path / "assets")
        asset_path.mkdir()
        Path(asset_path / "UUID").write_text(self._uuid)
        await git.add("assets/UUID")
        await git.commit("-am", "Add git-lfs tracked assets")

    async def _install_git_lfs(self, git: Git, scope: str = "--local") -> None:
        """Separate method so we can mock it out for testing and run
        without git-lfs.

        This takes the git client as a parameter because the scope is variable.
        Usually we will want to install it locally (hence "--local"), but
        for the clone into the repo after the Git LFS artifacts are uploaded,
        it is helpful to install git-lfs "globally" (really, using an
        ephemeral GIT_CONFIG_GLOBAL file, so it doesn't mess with the local
        development environment) so that the clone gets the LFS-stored item
        without a lot of tedious messing around inside the repository.  This
        is done by combining an empty scope string and a custom config_location
        on the git client.
        """
        await git.lfs("install", scope)

    async def _add_git_lfs_data(self, git: Git) -> None:
        if git.repo is None:
            raise ValueError("Git client repository cannot be 'None'")
        with self.timings.start("git attribute installation"):
            shutil.copyfile(
                Path(self._package_data / "gitattributes"),
                Path(git.repo / ".gitattributes"),
            )
            await git.add(".gitattributes")
            await git.config("--local", "lfs.url", self._lfs_write_url)

    async def _add_credentials(self, git: Git) -> None:
        credfile = Path(self._working_dir / ".git_credentials")
        credfile.touch()
        credfile.chmod(0o700)
        w_url = urlparse(self._lfs_write_url)
        await git.config(
            "--local",
            f"credential.{w_url.scheme}://{w_url.netloc}.helper",
            f"store --file {credfile!s}",
        )
        creds = f"{w_url.scheme}://gituser:{self.user.token}@{w_url.netloc}\n"
        credfile.write_text(creds)

    async def _verify_origin_contents(self) -> None:
        origin = Path(self._working_dir / "origin")
        # Verify the README, which should be the same whether or not we
        # used git-lfs
        srcdata = Path(self._package_data / "README.md").read_text()
        # We need to do a git reset to get HEAD back in sync.
        # This is what git warns you about and why we set
        # receive.denyCurrentBranch = ignore in the stock gitconfig.
        git = self._git(repo=origin)
        await git.reset("--hard")
        destdata = Path(origin / "README.md").read_text()
        if srcdata != destdata:
            raise ComparisonError(expected=srcdata, received=destdata)
        await self._check_uuid_pointer()

    async def _check_uuid_pointer(self) -> None:
        """Separate method so that we can replace it for testing.

        If git-lfs were not installed, we would expect the UUID file
        to contain the UUID rather than a pointer.
        """
        origin = Path(self._working_dir / "origin")
        srcdata = "version https://git-lfs.github.com/spec/v1"
        destdata = Path(origin / "assets" / "UUID").read_text()
        first = destdata.split("\n")[0]
        if srcdata != first:
            raise ComparisonError(expected=srcdata, received=destdata)

    async def _verify_asset_contents(self) -> None:
        """Verify that the cloned UUID file contains the actual UUID.

        It should whether it was stored directly or via git-lfs.
        """
        clone = Path(self._working_dir / "clone")
        srcdata = self._uuid
        destdata = Path(clone / "assets" / "UUID").read_text()
        if srcdata != destdata:
            raise ComparisonError(expected=srcdata, received=destdata)
