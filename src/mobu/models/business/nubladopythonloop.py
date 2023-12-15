"""Models for the NubladoPythonLoop monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .nublado import NubladoBusinessOptions

__all__ = [
    "NubladoPythonLoopConfig",
    "NubladoPythonLoopOptions",
]


class NubladoPythonLoopOptions(NubladoBusinessOptions):
    """Options for NubladoPythonLoop monkey business."""

    code: str = Field(
        'print(2+2, end="")',
        title="Python code to execute",
        examples=['print(2+2, end="")'],
    )

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            "The number of code snippets to execute before restarting the lab."
        ),
        examples=[25],
        ge=1,
    )


class NubladoPythonLoopConfig(BusinessConfig):
    """Configuration specialization for NubladoPythonLoop."""

    type: Literal["NubladoPythonLoop"] = Field(
        ..., title="Type of business to run"
    )

    options: NubladoPythonLoopOptions = Field(
        default_factory=NubladoPythonLoopOptions,
        title="Options for the monkey business",
    )
