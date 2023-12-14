"""Models for the TAPQueryRunner monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .tap import TAPBusinessOptions

__all__ = [
    "TAPQueryRunnerConfig",
    "TAPQueryRunnerOptions",
]


class TAPQueryRunnerOptions(TAPBusinessOptions):
    """Options for TAPQueryRunner monkey business."""

    queries: list[str] = Field(
        ...,
        title="TAP queries",
        description="List of queries to be run",
        example=[
            "SELECT TOP 10 * FROM TAP_SCHEMA.schemas",
            "SELECT TOP 10 * FROM MYDB.MyTable",
        ],
    )


class TAPQueryRunnerConfig(BusinessConfig):
    """Configuration specialization for TAPQueryRunner."""

    type: Literal["TAPQueryRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: TAPQueryRunnerOptions = Field(
        ..., title="Options for the monkey business"
    )
