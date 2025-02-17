"""Base models for SIA-related monkey business."""

from __future__ import annotations

from astropy.time import Time
from pydantic import BaseModel, Field

from .base import BusinessData

__all__ = ["SIA2Query", "SIABusinessData"]


class SIA2Query(BaseModel):
    """The parameters of an SIAv2 query."""

    ra: float
    dec: float
    radius: float
    time: list[float]

    @property
    def pos(self) -> tuple[float, float, float]:
        return self.ra, self.dec, self.radius

    def to_pyvo_sia2_params(self) -> dict:
        """Return the query as a dictionary in a form that
        pyvo's SIA2 search expects it. We transform the time strings to
        astropy Time objects and then to datetime.

        Returns
        -------
            dict: The query as a dictionary.
        """
        times = [Time(str(t), format="mjd").to_datetime() for t in self.time]
        return {"pos": self.pos, "time": times}

    def __str__(self) -> str:
        """Return a string representation of the query."""
        times = ", ".join([str(t) for t in self.time])
        return f"SIAv2 parameters: pos={self.pos}, time=[{times}])"


class SIABusinessData(BusinessData):
    """Status of a running SIA business."""

    running_query: SIA2Query | None = Field(
        None,
        title="Currently running query",
        description="Will not be present if no query is being executed",
    )
