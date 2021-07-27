"""Models for timing data."""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class PreviousStopwatchData(BaseModel):
    """Information about the predecessor to a timing event."""

    event: str = Field(..., title="Name of the event", example="hub_login")

    start: datetime = Field(
        ..., title="Start of event", example="2021-07-21T19:42:40.099495+00:00"
    )


class StopwatchData(BaseModel):
    """Timing for a single event."""

    event: str = Field(..., title="Name of the event", example="lab_create")

    annotation: Dict[str, str] = Field(
        default_factory=dict,
        title="Event annotations",
        example={"notebook": "example.ipynb"},
    )

    start: datetime = Field(
        ..., title="Start of event", example="2021-07-21T19:43:40.446072+00:00"
    )

    stop: Optional[datetime] = Field(
        None,
        title="End of event",
        description="Will be null if the event is ongoing",
        example="2021-07-21T19:43:40.514623+00:00",
    )

    elapsed: float = Field(
        None,
        title="Duration of event in seconds",
        description="Will be null if the event is ongoing",
        example=0.068551,
    )

    previous: Optional[PreviousStopwatchData] = Field(
        None, title="Previous event (if available)"
    )

    elapsed_since_previous_stop: Optional[float] = Field(
        None,
        title="Time between end of previous event and start in seconds",
        example=60.267267,
    )
