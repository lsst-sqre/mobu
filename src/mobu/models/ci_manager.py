"""Models for CiManager."""

from pydantic import BaseModel, Field, HttpUrl

from .user import User

__all__ = [
    "CiJobSummary",
    "CiManagerSummary",
    "CiWorkerSummary",
]


class CiJobSummary(BaseModel):
    """Information about a job."""

    commit_url: HttpUrl = Field(
        ...,
        title="GitHub URL to the commit being worked on",
    )


class CiWorkerSummary(BaseModel):
    """Information about a running worker."""

    user: User = Field(..., title="User that the worker works as")

    num_processed: int = Field(
        ...,
        title="Number of jobs this worker has processed since mobu started",
    )

    current_job: CiJobSummary | None = Field(
        ..., title="The job the worker is currently running, if any"
    )


class CiManagerSummary(BaseModel):
    """Information about the CiManager."""

    workers: list[CiWorkerSummary] = Field(
        ..., title="The workers being managed"
    )

    num_queued: int = Field(
        ..., title="Number of jobs waiting for a free worker"
    )
