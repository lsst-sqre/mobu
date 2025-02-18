"""Base models for monkey business."""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field
from safir.logging import LogLevel
from safir.pydantic import HumanTimedelta

__all__ = [
    "BusinessConfig",
    "BusinessData",
    "BusinessOptions",
]


class BusinessOptions(BaseModel):
    """Options for monkey business."""

    model_config = ConfigDict(extra="forbid")

    error_idle_time: HumanTimedelta = Field(
        timedelta(minutes=1),
        title="How long to wait after an error before restarting",
        examples=[600],
    )

    idle_time: HumanTimedelta = Field(
        timedelta(minutes=1),
        title="How long to wait between business executions",
        description=(
            "After each loop executing monkey business, the monkey will"
            " pause for this long"
        ),
        examples=[60],
    )

    log_level: LogLevel = Field(
        LogLevel.INFO,
        title="Log level for this monkey business",
    )


class BusinessConfig(BaseModel):
    """Base configuration class for monkey business.

    Each type of business must override this class, redefining ``type`` with a
    different literal and ``options`` with a different type and default
    factory.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., title="Type of business to run")

    options: BusinessOptions = Field(
        default_factory=BusinessOptions,
        title="Options for the monkey business",
    )

    restart: bool = Field(
        False, title="Restart business after failure", examples=[True]
    )


class BusinessData(BaseModel):
    """Status of a running business.

    Each type of business with additional data should create a new type
    inheriting from this type and adding that information.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., title="Type of business", examples=["Business"])

    failure_count: int = Field(..., title="Number of failures", examples=[0])

    success_count: int = Field(..., title="Number of successes", examples=[25])

    refreshing: bool = Field(
        ..., title="If the business is currently in the process of refreshing"
    )
