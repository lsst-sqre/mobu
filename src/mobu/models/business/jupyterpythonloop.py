"""Models for the JupyterPythonLoop monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .nublado import NubladoBusinessOptions

__all__ = [
    "JupyterPythonLoopConfig",
    "JupyterPythonLoopOptions",
]


class JupyterPythonLoopOptions(NubladoBusinessOptions):
    """Options for JupyterPythonLoop monkey business."""

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


class JupyterPythonLoopConfig(BusinessConfig):
    """Configuration specialization for JupyterPythonLoop."""

    type: Literal["JupyterPythonLoop"] = Field(
        ..., title="Type of business to run"
    )

    options: JupyterPythonLoopOptions = Field(
        default_factory=JupyterPythonLoopOptions,
        title="Options for the monkey business",
    )
