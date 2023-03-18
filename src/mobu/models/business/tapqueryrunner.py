"""Models for the TAPQueryRunner monkey business."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .base import BusinessConfig, BusinessData, BusinessOptions

__all__ = [
    "TAPQueryRunnerConfig",
    "TAPQueryRunnerData",
    "TAPQueryRunnerOptions",
]


class TAPQueryRunnerOptions(BusinessOptions):
    """Options for TAPQueryRunner monkey business."""

    query_set: str = Field(
        "dp0.1",
        title="Which query template set to use for a TapQueryRunner",
        example="dp0.2",
    )

    sync: bool = Field(
        True,
        title="Whether to run TAP queries as sync or async",
        description=(
            "By default, queries to TAP are run via the sync endpoint."
            " Set this to false to run as an async query."
        ),
        example=True,
    )


class TAPQueryRunnerConfig(BusinessConfig):
    """Configuration specialization for TAPQueryRunner."""

    type: Literal["TAPQueryRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: TAPQueryRunnerOptions = Field(
        default_factory=TAPQueryRunnerOptions,
        title="Options for the monkey business",
    )


class TAPQueryRunnerData(BusinessData):
    """Status of a running TAPQueryRunner business."""

    running_query: Optional[str] = Field(
        None,
        title="Currently running query",
        description="Will not be present if no query is being executed",
    )
