"""Models for timing data."""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer


class StopwatchData(BaseModel):
    """Timing for a single event."""

    event: str = Field(..., title="Name of the event", examples=["lab_create"])

    annotations: dict[str, str] = Field(
        default_factory=dict,
        title="Event annotations",
        examples=[{"notebook": "example.ipynb"}],
    )

    start: datetime = Field(
        ...,
        title="Start of event",
        examples=["2021-07-21T19:43:40.446072+00:00"],
    )

    stop: datetime | None = Field(
        None,
        title="End of event",
        description="Will be null if the event is ongoing",
        examples=["2021-07-21T19:43:40.514623+00:00"],
    )

    elapsed: Annotated[
        timedelta | None,
        PlainSerializer(
            lambda v: v.total_seconds() if v is not None else None,
            return_type=float,
            when_used="json",
        ),
    ] = Field(
        None,
        title="Duration of event",
        description="Will be null if the event is ongoing",
        examples=[0.068551],
    )

    failed: bool = Field(
        False, title="Whether the event failed", examples=[False]
    )
