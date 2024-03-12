"""Base models for Git-LFS-related monkey business."""

from typing import Literal

from pydantic import Field

from .base import BusinessConfig, BusinessOptions

__all__ = ["GitLFSBusinessOptions", "GitLFSConfig"]


class GitLFSBusinessOptions(BusinessOptions):
    """Options for business that runs git LFS operations."""

    lfs_read_url: str = Field(
        "https://git-lfs.lsst.cloud/mobu/git-lfs-test",
        title="LFS read URL for Git-LFS enabled repo",
    )
    lfs_write_url: str = Field(
        "https://git-lfs-rw.lsst.cloud/mobu/git-lfs-test",
        title="LFS write URL for Git-LFS enabled repo",
    )
    skip_lfs: bool = Field(
        False,
        title="Skip LFS operations (for testing only)",
    )


class GitLFSConfig(BusinessConfig):
    """Configuration specialization for GitLFS."""

    type: Literal["GitLFS"] = Field(..., title="Type of business to run")

    options: GitLFSBusinessOptions = Field(
        ..., title="Options for the GitLFS Business"
    )
