"""Models for timing data."""

from datetime import datetime

from pydantic import BaseModel, Field


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

    elapsed: float | None = Field(
        None,
        title="Duration of event in seconds",
        description="Will be null if the event is ongoing",
        examples=[0.068551],
    )

    failed: bool = Field(
        False, title="Whether the event failed", examples=[False]
    )
