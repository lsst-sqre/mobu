"""Base models for Git-LFS-related monkey business."""

from pydantic import Field

from .base import BusinessOptions

__all__ = ["GitLFSBusinessOptions"]


class GitLFSBusinessOptions(BusinessOptions):
    """Options for business that runs git LFS operations."""

    lfs_read_url: str = Field(
        "https://git-lfs.lsst.cloud/mobu/git-lfs-test",
        title="LFS read URL for Git-LFS enabled repo",
        description="URL endpoint for Git LFS reads.",
    )
    lfs_write_url: str = Field(
        "https://git-lfs-rw.lsst.cloud/mobu/git-lfs-test",
        title="LFS write URL for Git-LFS enabled repo",
        description="URL endpoint for Git LFS writes.",
    )
