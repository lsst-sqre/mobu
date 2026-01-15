"""Base models for TAP-related monkey business."""

from __future__ import annotations

from pydantic import Field

from .base import BusinessData, BusinessOptions

__all__ = [
    "TAPBusinessData",
    "TAPBusinessOptions",
]


class TAPBusinessOptions(BusinessOptions):
    """Options for any business that runs TAP queries."""

    dataset: str = Field("dp02", title="Data set to query", examples=["dp1"])

    sync: bool = Field(
        True,
        title="Whether to run TAP queries as sync or async",
        description=(
            "By default, queries to TAP are run via the sync endpoint."
            " Set this to false to run as an async query."
        ),
        examples=[True],
    )


class TAPBusinessData(BusinessData):
    """Status of a running TAPQueryRunner business."""

    running_query: str | None = Field(
        None,
        title="Currently running query",
        description="Will not be present if no query is being executed",
    )
