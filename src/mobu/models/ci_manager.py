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
        title="Commit URL",
        description="GitHub URL to the commit being worked on",
        examples=[
            (
                "https://github.com/lsst-sqre/mobu/commit/"
                "dd534286bb932dd22d61f97f960a5985b7513ec8"
            )
        ],
    )


class CiWorkerSummary(BaseModel):
    """Information about a running worker."""

    user: User = Field(
        ...,
        title="User",
        description="User that the worker works as",
        examples=[
            User(username="someuser", uidnumber=None, gidnumber=None),
            User(username="someuser", uidnumber=123, gidnumber=456),
        ],
    )

    num_processed: int = Field(
        ...,
        title="Number of jobs processed",
        description=(
            "Number of jobs this worker has processed since mobu started"
        ),
        examples=[123],
    )

    current_job: CiJobSummary | None = Field(
        ...,
        title="Current job summary",
        description="The job the worker is currently running, if any",
        examples=[
            CiJobSummary(
                commit_url=HttpUrl(
                    "https://github.com/lsst-sqre/mobu/commit/"
                    "dd534286bb932dd22d61f97f960a5985b7513ec8"
                ),
            )
        ],
    )


class CiManagerSummary(BaseModel):
    """Information about the CiManager."""

    workers: list[CiWorkerSummary] = Field(
        ...,
        title="Background workers",
        description="The workers being managed",
        examples=[
            [
                CiWorkerSummary(
                    user=User(
                        username="someuser", uidnumber=123, gidnumber=456
                    ),
                    num_processed=123,
                    current_job=CiJobSummary(
                        commit_url=HttpUrl(
                            "https://github.com/lsst-sqre/mobu/commit/"
                            "dd534286bb932dd22d61f97f960a5985b7513ec8"
                        ),
                    ),
                )
            ]
        ],
    )

    num_queued: int = Field(
        ...,
        title="Queued jobs",
        description="Number of jobs waiting for a free worker",
        examples=[123],
    )
