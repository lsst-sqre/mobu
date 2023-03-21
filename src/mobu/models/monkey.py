"""Data models for a monkey."""

from enum import Enum

from pydantic import BaseModel, Field

from .business.base import BusinessData
from .business.notebookrunner import NotebookRunnerData
from .business.nublado import NubladoBusinessData
from .business.tapqueryrunner import TAPQueryRunnerData
from .user import AuthenticatedUser


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

    state: MonkeyState = Field(
        ..., title="State of monkey", example=MonkeyState.RUNNING
    )

    user: AuthenticatedUser = Field(
        ..., title="User as which the monkey is running"
    )

    # These types should be given in order of most specific to least specific
    # to avoid the risk that Pydantic plus FastAPI will interpret a class as
    # its parent class.
    business: (
        TAPQueryRunnerData
        | NotebookRunnerData
        | NubladoBusinessData
        | BusinessData
    ) = Field(..., title="Business execution data")
