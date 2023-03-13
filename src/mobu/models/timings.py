"""Models for timing data."""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class StopwatchData(BaseModel):
    """Timing for a single event."""

    event: str = Field(..., title="Name of the event", example="lab_create")

    annotations: Dict[str, str] = Field(
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

    elapsed: Optional[float] = Field(
        None,
        title="Duration of event in seconds",
        description="Will be null if the event is ongoing",
        example=0.068551,
    )

    failed: bool = Field(
        False, title="Whether the event failed", example=False
    )
