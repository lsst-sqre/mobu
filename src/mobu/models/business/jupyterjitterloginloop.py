"""Models for the JupyterJitterLoginLoop monkey business."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import BusinessConfig
from .jupyterloginloop import JupyterLoginLoopOptions

__all__ = ["JupyterJitterLoginLoopConfig"]


class JupyterJitterLoginLoopConfig(BusinessConfig):
    """Configuration specialization for JupyterJitterLoginLoop.

    Notes
    -----
    `~mobu.services.business.jupyterjitterloginloop.JupyterJitterLoginLoop`
    takes no additional configuration options on top of the ones already
    defined in `~mobu.models.business.JupyterLoginLoopOptions`, so reuse the
    options type.
    """

    type: Literal["JupyterJitterLoginLoop"] = Field(
        ..., title="Type of business to run"
    )

    options: JupyterLoginLoopOptions = Field(
        default_factory=JupyterLoginLoopOptions,
        title="Options for the monkey business",
    )
