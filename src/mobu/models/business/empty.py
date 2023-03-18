"""Models for the EmptyLoop business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig

__all__ = ["EmptyLoopConfig"]


class EmptyLoopConfig(BusinessConfig):
    """Configuration specialization for EmptyLoop.

    This business class does nothing, successfully. It is used primarily for
    testing mobu.
    """

    type: Literal["EmptyLoop"] = Field(..., title="Type of business to run")
