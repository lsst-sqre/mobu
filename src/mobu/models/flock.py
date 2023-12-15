"""Models for a collection of monkeys."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from .business.empty import EmptyLoopConfig
from .business.jupyterpythonloop import JupyterPythonLoopConfig
from .business.notebookrunner import NotebookRunnerConfig
from .business.tapqueryrunner import TAPQueryRunnerConfig
from .business.tapquerysetrunner import TAPQuerySetRunnerConfig
from .monkey import MonkeyData
from .user import User, UserSpec


class FlockConfig(BaseModel):
    """Configuration for a flock of monkeys.

    A flock must all share the same business and options, but may contain any
    number of individual monkeys, which will all run as different users.
    """

    name: str = Field(..., title="Name of the flock", examples=["autostart"])

    count: int = Field(..., title="How many monkeys to run", examples=[100])

    users: list[User] | None = Field(
        None,
        title="Explicit list of users to run as",
        description=(
            "Run as the specific list of users. If specified, the length of"
            " the list must equal the count of monkeys to run. Specify either"
            " this or user_spec but not both."
        ),
    )

    user_spec: UserSpec | None = Field(
        None,
        title="Specification to generate users",
        description="Specify either this or users but not both",
    )

    scopes: list[str] = Field(
        ...,
        title="Token scopes",
        description="Must include all scopes required to run the business",
        examples=[["exec:notebook", "read:tap"]],
    )

    business: (
        TAPQueryRunnerConfig
        | TAPQuerySetRunnerConfig
        | NotebookRunnerConfig
        | JupyterPythonLoopConfig
        | EmptyLoopConfig
    ) = Field(..., title="Business to run")

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.users and not self.user_spec:
            raise ValueError("one of users or user_spec must be provided")
        if self.users and self.user_spec:
            raise ValueError("both users and user_spec provided")
        if self.count and self.users and len(self.users) != self.count:
            raise ValueError(f"users list must contain {self.count} elements")
        return self


class FlockData(BaseModel):
    """Information about a running flock."""

    name: str = Field(..., title="Name of the flock", examples=["autostart"])

    config: FlockConfig = Field(..., title="Configuration for the flock")

    monkeys: list[MonkeyData] = Field(..., title="Monkeys of the flock")


class FlockSummary(BaseModel):
    """Summary statistics about a running flock."""

    name: str = Field(..., title="Name of the flock", examples=["autostart"])

    business: str = Field(
        ...,
        title="Name of the business the flock is running",
        examples=["NotebookRunner"],
    )

    start_time: datetime | None = Field(
        ...,
        title="When the flock was started",
        description="Will be null if the flock hasn't started",
        examples=["2021-07-21T19:43:40.446072+00:00"],
    )

    monkey_count: int = Field(
        ..., title="Number of monkeys in the flock", examples=[5]
    )

    success_count: int = Field(
        ..., title="Total number of monkey successes in flock", examples=[455]
    )

    failure_count: int = Field(
        ..., title="Total number of monkey failures in flock", examples=[4]
    )
