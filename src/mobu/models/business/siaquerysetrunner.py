"""Models for the SIAQuerySetRunner monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .sia import SIABusinessOptions

__all__ = [
    "SIAQuerySetRunnerConfig",
    "SIAQuerySetRunnerOptions",
]


class SIAQuerySetRunnerOptions(SIABusinessOptions):
    """Options for SIAQuerySetRunner monkey business."""

    query_set: str = Field(
        "dp02",
        title="Which query template set to use for a SIAQuerySetRunner",
        examples=["dp02"],
    )


class SIAQuerySetRunnerConfig(BusinessConfig):
    """Configuration specialization for SIAQuerySetRunner."""

    type: Literal["SIAQuerySetRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: SIAQuerySetRunnerOptions = Field(
        default_factory=SIAQuerySetRunnerOptions,
        title="Options for the monkey business",
    )
