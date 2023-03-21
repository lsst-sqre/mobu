"""Base models for Nublado-related monkey business."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from ..jupyter import JupyterConfig, JupyterImage
from .base import BusinessData, BusinessOptions

__all__ = [
    "NubladoBusinessData",
    "NubladoBusinessOptions",
]


class NubladoBusinessOptions(BusinessOptions):
    """Options for any business that runs code in a Nublado lab."""

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

    execution_idle_time: int = Field(
        1,
        title="How long to wait between cell executions in seconds",
        description="Used by JupyterPythonLoop and NotebookRunner",
        example=1,
    )

    get_node: bool = Field(
        True,
        title="Whether to get the node name for error reporting",
        description=(
            "Used by JupyterPythonLoop and its subclasses. Requires the lab"
            " have rubin_jupyter_utils.lab.notebook.utils pre-installed and"
            " able to make Kubernetes API calls."
        ),
    )

    jitter: int = Field(
        0,
        title="Maximum random time to pause",
        description=(
            "If set to a non-zero value, pause for a random interval between"
            " 0 and that many seconds before logging in to JupyterHub, and"
            " between each iteration of the core execution loop. Use this when"
            " running lots of monkeys for load testing to spread their"
            " execution sequence out more realistically and avoid a thundering"
            " herd problem."
        ),
        example=60,
    )

    jupyter: JupyterConfig = Field(
        default_factory=JupyterConfig,
        title="Jupyter lab spawning configuration",
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

    working_directory: Optional[str] = Field(
        None,
        title="Working directory when running code",
        example="notebooks/tutorial-notebooks",
    )


class NubladoBusinessData(BusinessData):
    """Status of a running Nublado business."""

    image: Optional[JupyterImage] = Field(
        None,
        title="JupyterLab image information",
        description="Will only be present when there is an active Jupyter lab",
    )
