"""Base models for monkey business."""

from datetime import timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from ..timings import StopwatchData

__all__ = [
    "BusinessConfig",
    "BusinessOptions",
    "BusinessData",
    "SerializableTimedelta",
]

SerializableTimedelta = Annotated[
    timedelta,
    PlainSerializer(
        lambda v: round(v.total_seconds()), return_type=int, when_used="json"
    ),
]


class BusinessOptions(BaseModel):
    """Options for monkey business."""

    error_idle_time: SerializableTimedelta = Field(
        timedelta(minutes=1),
        title="How long to wait after an error before restarting",
        examples=[600],
    )

    idle_time: SerializableTimedelta = Field(
        timedelta(minutes=1),
        title="How long to wait between business executions",
        description=(
            "AFter each loop executing monkey business, the monkey will"
            " pause for this long"
        ),
        examples=[60],
    )

    model_config = ConfigDict(extra="forbid")


class BusinessConfig(BaseModel):
    """Base configuration class for monkey business.

    Each type of business must override this class, redefining ``type`` with a
    different literal and ``options`` with a different type and default
    factory.
    """

    type: str = Field(..., title="Type of business to run")

    options: BusinessOptions = Field(
        default_factory=BusinessOptions,
        title="Options for the monkey business",
    )

    restart: bool = Field(
        False, title="Restart business after failure", examples=[True]
    )

    model_config = ConfigDict(extra="forbid")


class BusinessData(BaseModel):
    """Status of a running business.

    Each type of business with additional data should create a new type
    inheriting from this type and adding that information.
    """

    name: str = Field(..., title="Type of business", examples=["Business"])

    failure_count: int = Field(..., title="Number of failures", examples=[0])

    success_count: int = Field(..., title="Number of successes", examples=[25])

    timings: list[StopwatchData] = Field(..., title="Timings of events")

    model_config = ConfigDict(extra="forbid")
