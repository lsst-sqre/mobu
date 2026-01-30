"""Models for the Muster monkey business."""

from typing import Literal

from pydantic import Field

from .base import BusinessConfig, BusinessOptions

__all__ = [
    "MusterConfig",
    "MusterOptions",
]


class MusterOptions(BusinessOptions):
    """Options for the Muster monkey business."""


class MusterConfig(BusinessConfig):
    """Configuration specialization for Muster."""

    type: Literal["Muster"] = Field(..., title="Type of business to run")

    options: MusterOptions = Field(
        default_factory=MusterOptions, title="Options for the monkey business"
    )
