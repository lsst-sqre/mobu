"""Data models for a monkey."""

from enum import Enum

from pydantic import BaseModel, Field

from .business import BusinessConfig, BusinessData
from .user import AuthenticatedUser, UserConfig


class MonkeyConfig(BaseModel):
    """Configuration for a single monkey."""

    name: str = Field(
        ...,
        title="Name of the monkey",
        description="This need not match the username as which it runs",
        example="monkey01",
    )

    user: UserConfig = Field(
        ..., title="User whose credentials the monkey will use"
    )

    business: str = Field(..., title="Type of business to run")

    options: BusinessConfig = Field(
        default_factory=BusinessConfig, title="Business to run"
    )

    restart: bool = Field(
        False, title="Restart business after failure", example=True
    )


class MonkeyState(Enum):
    """State of a running monkey."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class MonkeyData(BaseModel):
    """Data for a running monkey."""

    name: str = Field(..., title="Name of the monkey")

    business: BusinessData = Field(..., title="Business execution data")

    restart: bool = Field(..., title="Restart on error")

    state: MonkeyState = Field(
        ..., title="State of monkey", example=MonkeyState.RUNNING
    )

    user: AuthenticatedUser = Field(
        ..., title="User as which the monkey is running"
    )
