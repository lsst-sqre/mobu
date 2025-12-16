"""Models for the SIAQuerySetRunner monkey business."""

from __future__ import annotations

from typing import Literal, override

from astropy.time import Time
from pydantic import BaseModel, Field

from .base import BusinessConfig, BusinessData, BusinessOptions

__all__ = [
    "SIABusinessData",
    "SIAQuery",
    "SIAQuerySetRunnerConfig",
    "SIAQuerySetRunnerOptions",
]


class SIAQuerySetRunnerOptions(BusinessOptions):
    """Options for SIAQuerySetRunner monkey business."""

    query_set: str = Field(
        "dp02",
        title="Which query template set to use for a SIAQuerySetRunner",
        examples=["dp02"],
    )


class SIAQuerySetRunnerConfig(BusinessConfig):
    """Configuration specialization for SIAQuerySetRunner."""

    type: Literal["SIAQuerySetRunner"] = Field(
        ..., title="Type of business to run"
    )

    options: SIAQuerySetRunnerOptions = Field(
        default_factory=SIAQuerySetRunnerOptions,
        title="Options for the monkey business",
    )


class SIAQuery(BaseModel):
    """The parameters of an SIA (v2) query."""

    ra: float
    dec: float
    radius: float
    time: list[float]

    @property
    def pos(self) -> tuple[float, float, float]:
        return self.ra, self.dec, self.radius

    def to_pyvo_sia_params(self) -> dict:
        """Return the query as a dictionary in a form that
        pyvo's SIA search expects it. We transform the time strings to
        astropy Time objects and then to datetime.

        Returns
        -------
        dict
            The query as a dictionary.
        """
        times = [Time(str(t), format="mjd").to_datetime() for t in self.time]
        return {"pos": self.pos, "time": times}

    @override
    def __str__(self) -> str:
        """Return a string representation of the query."""
        times = ", ".join([str(t) for t in self.time])
        return f"SIA parameters: pos={self.pos}, time=[{times}])"


class SIABusinessData(BusinessData):
    """Status of a running SIA business."""

    running_query: SIAQuery | None = Field(
        None,
        title="Currently running query",
        description="Will not be present if no query is being executed",
    )
