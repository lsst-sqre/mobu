"""A base model for FROGMAP events."""

from pydantic import AwareDatetime, BaseModel, Field, PlainSerializer

Value = PlainSerializer(func=lambda x: {"type": "field", "value": x})

Attribute = PlainSerializer(func=lambda x: {"type": "tag", "value": x})


class Payload(BaseModel):
    """Event payload with runtime correctness validation."""

    @classmethod
    def validate_field_types(cls) -> None:
        for field_name, field_type in cls.__annotations__.items():
            if not getattr(field_type, "__metadata__", None) or bool(
                {Attribute, Value} & set(field_type.__metadata__)
            ):
                raise TypeError(
                    f"{field_name}: All fields of this model must be annotated"
                    " with either Value or Attribute. See TODO."
                )


class EventModel[P: Payload](BaseModel):
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

    payload: P = Field(
        ...,
        description=(
            "A model containing attributes (which can be filtered on) and"
            " values (which can be aggregated)"
        ),
    )
