"""Models for running a single instance of a business by itself."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .business.empty import EmptyLoopConfig
from .business.notebookrunner import NotebookRunnerConfig
from .business.nubladopythonloop import NubladoPythonLoopConfig
from .business.tapqueryrunner import TAPQueryRunnerConfig
from .user import User


class SolitaryConfig(BaseModel):
    """Configuration for a solitary monkey.

    This is similar to `~mobu.models.flock.FlockConfig`, but less complex
    since it can only wrap a single monkey business.
    """

    user: User = Field(..., title="User to run as")

    scopes: list[str] = Field(
        ...,
        title="Token scopes",
        description="Must include all scopes required to run the business",
        examples=[["exec:notebook", "read:tap"]],
    )

    business: (
        TAPQueryRunnerConfig
        | NotebookRunnerConfig
        | NubladoPythonLoopConfig
        | EmptyLoopConfig
    ) = Field(..., title="Business to run")


class SolitaryResult(BaseModel):
    """Results from executing a solitary monkey."""

    success: bool = Field(..., title="Whether the business succeeded")

    error: str | None = Field(None, title="Error if the business failed")

    log: str = Field(..., title="Log of the business execution")
