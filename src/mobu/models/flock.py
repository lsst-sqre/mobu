"""Models for a collection of monkeys."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator

from .business import BusinessConfig
from .monkey import MonkeyConfig, MonkeyData
from .user import User, UserSpec


class FlockConfig(BaseModel):
    """Configuration for a flock of monkeys.

    A flock must all share the same business and options, but may contain any
    number of individual monkeys, which will all run as different users.
    """

    name: str = Field(..., title="Name of the flock", example="autostart")

    count: int = Field(..., title="How many monkeys to run", example=100)

    users: Optional[List[User]] = Field(
        None,
        title="Explicit list of users to run as",
        description=(
            "Run as the specific list of users. If specified, the length of"
            " the list must equal the count of monkeys to run. Specify either"
            " this or user_spec but not both."
        ),
    )

    user_spec: Optional[UserSpec] = Field(
        None,
        title="Specification to generate users",
        description="Specify either this or users but not both",
    )

    scopes: List[str] = Field(
        ...,
        title="Token scopes",
        description="Must include all scopes required to run the business",
        example=["exec:notebook", "read:tap"],
    )

    business: Literal[
        "Business",
        "JupyterJitterLoginLoop",
        "JupyterLoginLoop",
        "JupyterPythonLoop",
        "NotebookRunner",
        "SpawnTimerLoop",
        "TAPQueryRunner",
    ] = Field(..., title="Type of business to run")

    options: BusinessConfig = Field(
        default_factory=BusinessConfig, title="Business to run"
    )

    restart: bool = Field(
        False, title="Restart business after failure", example=True
    )

    @validator("users")
    def _valid_users(
        cls, v: Optional[List[User]], values: Dict[str, Any]
    ) -> Optional[List[User]]:
        if v is None:
            return v
        if "count" in values and len(v) != values["count"]:
            count = values["count"]
            raise ValueError(f"users list must contain {count} elements")
        return v

    @validator("user_spec", always=True)
    def _valid_user_spec(
        cls, v: Optional[UserSpec], values: Dict[str, Any]
    ) -> Optional[UserSpec]:
        if v is None and ("users" not in values or values["users"] is None):
            raise ValueError("one of users or user_spec must be provided")
        if v and "users" in values and values["users"]:
            raise ValueError("both users and user_spec provided")
        return v

    def monkey_config(self, name: str) -> MonkeyConfig:
        """Create a configuration for a monkey in the flock."""
        return MonkeyConfig(
            name=name,
            business=self.business,
            options=self.options,
            restart=self.restart,
        )


class FlockData(BaseModel):
    """Information about a running flock."""

    name: str = Field(..., title="Name of the flock", example="autostart")

    config: FlockConfig = Field(..., title="Configuration for the flock")

    monkeys: List[MonkeyData] = Field(..., title="Monkeys of the flock")


class FlockSummary(BaseModel):
    """Summary statistics about a running flock."""

    name: str = Field(..., title="Name of the flock", example="autostart")

    business: str = Field(
        ...,
        title="Name of the business the flock is running",
        example="NotebookRunner",
    )

    start_time: Optional[datetime] = Field(
        ...,
        title="When the flock was started",
        description="Will be null if the flock hasn't started",
        example="2021-07-21T19:43:40.446072+00:00",
    )

    monkey_count: int = Field(
        ..., title="Number of monkeys in the flock", example=5
    )

    success_count: int = Field(
        ..., title="Total number of monkey successes in flock", example=455
    )

    failure_count: int = Field(
        ..., title="Total number of monkey failures in flock", example=4
    )
