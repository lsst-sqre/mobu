"""Models for the JupyterLoginLoop monkey business and subclasses."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from ..jupyter import JupyterConfig, JupyterImage
from .base import BusinessConfig, BusinessData, BusinessOptions

__all__ = [
    "JupyterLoginLoopConfig",
    "JupyterLoginLoopData",
    "JupyterLoginLoopOptions",
    "JupyterLoginOptions",
]


class JupyterLoginOptions(BusinessOptions):
    """Options for any business that creates Jupyter labs."""

    delete_lab: bool = Field(
        True,
        title="Whether to delete the lab between iterations",
        description=(
            "By default, the lab is deleted and recreated after each"
            " iteration of monkey business involving JupyterLab. Set this"
            " to False to keep the same lab."
        ),
        example=True,
    )

    delete_timeout: int = Field(
        60, title="Timeout for deleting a lab in seconds", example=60
    )

    jupyter: JupyterConfig = Field(
        default_factory=JupyterConfig,
        title="Jupyter lab spawning configuration",
    )

    lab_settle_time: int = Field(
        0,
        title="How long to wait after spawn before using a lab, in seconds",
        description=(
            "Wait this long after a lab successfully spawns before starting"
            " to use it"
        ),
        example=0,
    )

    spawn_settle_time: int = Field(
        10,
        title="How long to wait before polling spawn progress in seconds",
        description=(
            "Wait this long after triggering a lab spawn before starting to"
            " poll its progress. KubeSpawner 1.1.0 has a bug where progress"
            " queries prior to starting the spawn will fail with an exception"
            " that closes the progress EventStream."
        ),
        example=10,
    )

    spawn_timeout: int = Field(
        610, title="Timeout for spawning a lab in seconds", example=610
    )


class JupyterLoginLoopOptions(JupyterLoginOptions):
    """Options for JupyterLoginLoop monkey business."""

    login_idle_time: int = Field(
        60,
        title="Time to pause after spawning lab",
        description=(
            " How long to wait after spawning the lab before destroying"
            " it again."
        ),
        example=60,
    )


class JupyterLoginLoopConfig(BusinessConfig):
    """Configuration specialization for JupyterLoginLoop."""

    type: Literal["JupyterLoginLoop"] = Field(
        ..., title="Type of business to run"
    )

    options: JupyterLoginLoopOptions = Field(
        default_factory=JupyterLoginLoopOptions,
        title="Options for the monkey business",
    )


class JupyterLoginLoopData(BusinessData):
    """Status of a running JupyterLoginLoop business."""

    image: Optional[JupyterImage] = Field(
        None,
        title="JupyterLab image information",
        description="Will only be present when there is an active Jupyter lab",
    )
