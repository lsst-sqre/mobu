"""A base model for FROGMAP events."""

from pydantic import AwareDatetime, BaseModel, Field


class EventModel[A, V](BaseModel):
    """Base model for all events emitted by this service.

    Contains the minimum required fields.
    """

    name: str = Field(
        ...,
        description=(
            "The name of this event. Should be unique among all of the events"
            " in this service."
        ),
    )

    service: str = Field(
        ...,
        description="The application generating this event.",
        examples=["gafaelfawr", "mobu"],
    )

    timestamp: AwareDatetime = Field(
        ...,
        description=(
            "The time at which this event occurred, or the time at which this"
            " event completed if it is a duration event."
        ),
    )

    attributes: A | None = Field(
        None,
        description=(
            "An object containing non-aggregateable attributes about an event."
        ),
    )

    values: V | None = Field(
        None,
        description=(
            "An object containing aggregateable attributes about an event."
        ),
    )
