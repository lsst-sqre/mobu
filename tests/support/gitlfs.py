"""Functions and constants for mocking out git-lfs behavior."""

from contextlib import suppress
from pathlib import Path

from mobu.exceptions import ComparisonError, SubprocessError
from mobu.services.business.gitlfs import GitLFSBusiness
from mobu.storage.git import Git

flock_message = {
    "name": "test",
    "count": 1,
    "debug": "true",
    "user_spec": {"username_prefix": "bot-mobu-testuser"},
    "scopes": ["exec:notebook"],  # IRL it would need write:git-lfs
    "business": {
        "type": "GitLFS",
        "options": {
            "lfs_read_url": (
                "https://git-lfs-ro.example.com/mobu/git-lfs-test"
            ),
            "lfs_write_url": (
                "https://git-lfs-rw.example.com/mobu/git-lfs-test"
            ),
        },
    },
}


async def uninstall_git_lfs(
    self: GitLFSBusiness, git: Git, scope: str = "--local"
) -> None:
    """Ensure git lfs isn't around."""
    self.logger.info("Running lfs uninstall from MockGitLFSBusiness")
    # Git LFS might never have been installed in the first place.
    with suppress(SubprocessError):
        await git.lfs("uninstall", scope)


async def no_git_lfs_data(self: GitLFSBusiness, git: Git) -> None:
    pass


async def verify_uuid_contents(self: GitLFSBusiness) -> None:
    """Ensure that the origin UUID is the actual UUID string, not the
    git-lfs pointer.
    """
    origin = Path(self._working_dir / "origin")
    srcdata = self._uuid
    destdata = Path(origin / "assets" / "UUID").read_text()
    if srcdata != destdata:
        raise ComparisonError(expected=srcdata, received=destdata)
