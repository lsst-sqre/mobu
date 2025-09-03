"""Models for running a single instance of a business by itself."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .business.business_config_type import BusinessConfigType
from .user import User

__all__ = ["SolitaryConfig", "SolitaryResult"]


class SolitaryConfig(BaseModel):
    """Configuration for a solitary monkey.

    This is similar to `~mobu.models.flock.FlockConfig`, but less complex
    since it can only wrap a single monkey business.
    """

    user: User = Field(..., title="User to run as")

    scopes: list[str] = Field(
        ...,
        title="Token scopes",
        description="Must include all scopes required to run the business",
        examples=[["exec:notebook", "read:tap"]],
    )

    business: BusinessConfigType = Field(
        ..., title="Business to run", discriminator="type"
    )


class SolitaryResult(BaseModel):
    """Results from executing a solitary monkey."""

    success: bool = Field(..., title="Whether the business succeeded")

    error: str | None = Field(None, title="Error if the business failed")

    log: str = Field(..., title="Log of the business execution")
