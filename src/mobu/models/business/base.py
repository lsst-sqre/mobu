"""Base models for monkey business."""

from pydantic import BaseModel, Extra, Field

from ..timings import StopwatchData

__all__ = [
    "BusinessConfig",
    "BusinessOptions",
    "BusinessData",
]


class BusinessOptions(BaseModel):
    """Options for monkey business.

    Each type of business should create its own options class that inherits
    from this class and adds any additional options that it supports.
    """

    idle_time: int = Field(
        60,
        title="How long to wait between business executions",
        description=(
            "AFter each loop executing monkey business, the monkey will"
            " pause for this long in seconds"
        ),
        example=60,
    )

    class Config:
        extra = Extra.forbid


class BusinessConfig(BaseModel):
    """Base configuration class for monkey business.

    Each type of business must override this class, redefining ``type`` with a
    different literal and ``options`` with a different type and default
    factory. This base class doubles as the configuration for the
    `~mobu.services.business.base.Business` base business class.
    """

    type: str = Field(..., title="Type of business to run")

    options: BusinessOptions = Field(
        default_factory=BusinessOptions,
        title="Options for the monkey business",
    )

    restart: bool = Field(
        False, title="Restart business after failure", example=True
    )


class BusinessData(BaseModel):
    """Status of a running business.

    Each type of business with additional data should create a new type
    inheriting from this type and adding that information.
    """

    name: str = Field(..., title="Type of business", example="Business")

    failure_count: int = Field(..., title="Number of failures", example=0)

    success_count: int = Field(..., title="Number of successes", example=25)

    timings: list[StopwatchData] = Field(..., title="Timings of events")

    class Config:
        extra = Extra.forbid
