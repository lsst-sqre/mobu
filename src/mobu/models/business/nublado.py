"""Base models for Nublado-related monkey business."""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from rubin.nublado.client import (
    NubladoImageByClass,
    NubladoImageByReference,
    NubladoImageByTag,
)
from safir.pydantic import HumanTimedelta

from .base import BusinessData, BusinessOptions

__all__ = [
    "NubladoBusinessData",
    "NubladoBusinessOptions",
    "RunningImage",
]


class NubladoBusinessOptions(BusinessOptions):
    """Options for any business that runs code in a Nublado lab."""

    delete_lab: bool = Field(
        True,
        title="Whether to delete the lab between iterations",
        description=(
            "By default, the lab is deleted and recreated after each"
            " iteration of monkey business. Set this to false to keep the"
            " same lab."
        ),
        examples=[True],
    )

    delete_timeout: HumanTimedelta = Field(
        timedelta(minutes=1), title="Timeout for deleting a lab", examples=[60]
    )

    execution_idle_time: HumanTimedelta = Field(
        timedelta(seconds=1),
        title="How long to wait between cell executions",
        description="Used by NubladoPythonLoop and NotebookRunner",
        examples=[1],
    )

    get_node: bool = Field(
        True,
        title="Whether to get the node name for error reporting",
        description=(
            "Used by NubladoPythonLoop and its subclasses. Requires the lab"
            " have lsst.rsp pre-installed."
        ),
    )

    image: (
        NubladoImageByClass | NubladoImageByReference | NubladoImageByTag
    ) = Field(
        default_factory=NubladoImageByClass, title="Nublado lab image to use"
    )

    jitter: HumanTimedelta = Field(
        timedelta(seconds=0),
        title="Maximum random time to pause",
        description=(
            "If set to a non-zero value, pause for a random interval between"
            " 0 and that interval before logging in to JupyterHub, and"
            " between each iteration of the core execution loop. Use this when"
            " running lots of monkeys for load testing to spread their"
            " execution sequence out more realistically and avoid a thundering"
            " herd problem."
        ),
        examples=[60],
    )

    jupyter_timeout: HumanTimedelta = Field(
        timedelta(minutes=1),
        title="HTTP client timeout for Jupyter requests",
        description=(
            "Used as the connect, read, and write timeout for talking to"
            " either JupyterHub or Jupyter lab."
        ),
    )

    max_websocket_message_size: int | None = Field(
        10 * 1024 * 1024,
        title="Maximum length of WebSocket message (in bytes)",
        description=(
            "This has to be large enough to hold HTML and image output from"
            " executing notebook cells, even though we discard that data."
            " Set to ``null`` for no limit."
        ),
    )

    spawn_settle_time: HumanTimedelta = Field(
        timedelta(seconds=10),
        title="How long to wait before polling spawn progress",
        description=(
            "Wait this long after triggering a lab spawn before starting to"
            " poll its progress. KubeSpawner 1.1.0 has a bug where progress"
            " queries prior to starting the spawn will fail with an exception"
            " that closes the progress EventStream."
        ),
        examples=[10],
    )

    spawn_timeout: HumanTimedelta = Field(
        timedelta(seconds=610),
        title="Timeout for spawning a lab",
        examples=[610],
    )

    url_prefix: str = Field("/nb/", title="URL prefix for JupyterHub")

    working_directory: str | None = Field(
        None,
        title="Working directory when running code",
        examples=["notebooks/tutorial-notebooks"],
    )


class RunningImage(BaseModel):
    """Information about the running Jupyter lab image."""

    reference: str | None = Field(
        None,
        title="Docker reference for the image",
    )

    description: str | None = Field(
        None,
        title="Human-readable description of the image",
    )


class NubladoBusinessData(BusinessData):
    """Status of a running Nublado business."""

    image: RunningImage | None = Field(
        None,
        title="Jupyter lab image information",
        description="Will only be present when there is an active Jupyter lab",
    )
