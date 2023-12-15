"""Models for the TAPQuerySetRunner monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .tap import TAPBusinessOptions

__all__ = [
    "TAPQuerySetRunnerConfig",
    "TAPQuerySetRunnerOptions",
]


class TAPQuerySetRunnerOptions(TAPBusinessOptions):
    """Options for TAPQueryRunner monkey business."""

    query_set: str = Field(
        "dp0.1",
        title="Which query template set to use for a TapQueryRunner",
        examples=["dp0.2"],
    )


class TAPQuerySetRunnerConfig(BusinessConfig):
    """Configuration specialization for TAPQuerySetRunner."""

    type: Literal["TAPQuerySetRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: TAPQuerySetRunnerOptions = Field(
        default_factory=TAPQuerySetRunnerOptions,
        title="Options for the monkey business",
    )
