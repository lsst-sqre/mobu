"""Base models for Git-LFS-related monkey business."""

from typing import Literal

from pydantic import Field

from .base import BusinessConfig, BusinessOptions

__all__ = ["GitLFSBusinessOptions", "GitLFSConfig"]


class GitLFSBusinessOptions(BusinessOptions):
    """Options for business that runs git LFS operations."""

    lfs_read_url: str = Field(
        ...,
        title="LFS read URL for Git-LFS enabled repo",
    )
    lfs_write_url: str = Field(
        ...,
        title="LFS write URL for Git-LFS enabled repo",
    )


class GitLFSConfig(BusinessConfig):
    """Configuration specialization for GitLFS."""

    type: Literal["GitLFS"] = Field(..., title="Type of business to run")

    options: GitLFSBusinessOptions = Field(
        ..., title="Options for the GitLFS Business"
    )
