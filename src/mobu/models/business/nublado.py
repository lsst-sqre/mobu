"""Base models for Nublado-related monkey business."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .base import BusinessData, BusinessOptions

__all__ = [
    "CachemachinePolicy",
    "NubladoBusinessData",
    "NubladoBusinessOptions",
    "NubladoImage",
    "NubladoImageByClass",
    "NubladoImageByReference",
    "NubladoImageByTag",
    "NubladoImageClass",
    "NubladoImageSize",
    "RunningImage",
]


class CachemachinePolicy(Enum):
    """Policy for what eligible images to retrieve from cachemachine."""

    available = "available"
    desired = "desired"


class NubladoImageClass(str, Enum):
    """Possible ways of selecting an image."""

    __slots__ = ()

    RECOMMENDED = "recommended"
    LATEST_RELEASE = "latest-release"
    LATEST_WEEKLY = "latest-weekly"
    LATEST_DAILY = "latest-daily"
    BY_REFERENCE = "by-reference"
    BY_TAG = "by-tag"


class NubladoImageSize(Enum):
    """Acceptable sizes of images to spawn."""

    Fine = "Fine"
    Diminutive = "Diminutive"
    Tiny = "Tiny"
    Small = "Small"
    Medium = "Medium"
    Large = "Large"
    Huge = "Huge"
    Gargantuan = "Gargantuan"
    Colossal = "Colossal"


class NubladoImage(BaseModel, metaclass=ABCMeta):
    """Base class for different ways of specifying the lab image to spawn."""

    # Ideally this would just be class, but it is a keyword and adding all the
    # plumbing to correctly serialize Pydantic models by alias instead of
    # field name is tedious and annoying. Live with the somewhat verbose name.
    image_class: NubladoImageClass = Field(
        ...,
        title="Class of image to spawn",
    )

    size: NubladoImageSize = Field(
        NubladoImageSize.Large,
        title="Size of image to spawn",
        description="Must be one of the sizes understood by Nublado.",
    )

    debug: bool = Field(False, title="Whether to enable lab debugging")

    @abstractmethod
    def to_spawn_form(self) -> dict[str, str]:
        """Convert to data suitable for posting to Nublado's spawn form.

        Returns
        -------
        dict of str
            Post data to send to the JupyterHub spawn page.
        """


class NubladoImageByClass(NubladoImage):
    """Spawn the recommended image."""

    image_class: Literal[
        NubladoImageClass.RECOMMENDED,
        NubladoImageClass.LATEST_RELEASE,
        NubladoImageClass.LATEST_WEEKLY,
        NubladoImageClass.LATEST_DAILY,
    ] = Field(
        NubladoImageClass.RECOMMENDED,
        title="Class of image to spawn",
    )

    def to_spawn_form(self) -> dict[str, str]:
        result = {
            "image_class": self.image_class.value,
            "size": self.size.value,
        }
        if self.debug:
            result["enable_debug"] = "true"
        return result


class NubladoImageByReference(NubladoImage):
    """Spawn an image by full Docker reference."""

    image_class: Literal[NubladoImageClass.BY_REFERENCE] = Field(
        NubladoImageClass.BY_REFERENCE, title="Class of image to spawn"
    )

    reference: str = Field(..., title="Docker reference of lab image to spawn")

    def to_spawn_form(self) -> dict[str, str]:
        result = {
            "image_list": self.reference,
            "size": self.size.value,
        }
        if self.debug:
            result["enable_debug"] = "true"
        return result


class NubladoImageByTag(NubladoImage):
    """Spawn an image by image tag."""

    image_class: Literal[NubladoImageClass.BY_TAG] = Field(
        NubladoImageClass.BY_TAG, title="Class of image to spawn"
    )

    tag: str = Field(..., title="Tag of image to spawn")

    def to_spawn_form(self) -> dict[str, str]:
        result = {"image_tag": self.tag, "size": self.size.value}
        if self.debug:
            result["enable_debug"] = "true"
        return result


class NubladoBusinessOptions(BusinessOptions):
    """Options for any business that runs code in a Nublado lab."""

    cachemachine_image_policy: CachemachinePolicy = Field(
        CachemachinePolicy.available,
        title="Class of cachemachine images to use",
        description=(
            "Whether to use the images available on all nodes, or the images"
            " desired by cachemachine. In instances where image streaming is"
            " enabled and therefore pulls are fast, ``desired`` is preferred."
            " The default is ``available``. Only used if ``use_cachemachine``"
            " is true."
        ),
        examples=[CachemachinePolicy.desired],
    )

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

    delete_timeout: int = Field(
        60, title="Timeout for deleting a lab in seconds", examples=[60]
    )

    execution_idle_time: int = Field(
        1,
        title="How long to wait between cell executions in seconds",
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
        examples=[60],
    )

    jupyter_timeout: int = Field(
        60,
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
            " Set to `null` for no limit."
        ),
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
        examples=[10],
    )

    spawn_timeout: int = Field(
        610, title="Timeout for spawning a lab in seconds", examples=[610]
    )

    url_prefix: str = Field("/nb/", title="URL prefix for JupyterHub")

    use_cachemachine: bool = Field(
        True,
        title="Whether to use cachemachine to look up an image",
        description=(
            "Set this to false in environments using the new Nublado lab"
            " controller."
        ),
        examples=[False],
    )

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
