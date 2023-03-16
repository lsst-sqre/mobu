"""Models for configuring a Jupyter lab."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Self

from pydantic import BaseModel, Field, validator

__all__ = ["JupyterConfig", "JupyterImage", "JupyterImageClass"]


class JupyterImageClass(Enum):
    """Possible ways of selecting an image."""

    RECOMMENDED = "recommended"
    LATEST_WEEKLY = "latest-weekly"
    BY_REFERENCE = "by-reference"


class JupyterImage(BaseModel):
    """Represents an image to spawn as a Jupyter Lab."""

    reference: str = Field(
        ...,
        title="Docker reference for the image",
        example="registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13",
    )

    name: str = Field(
        ...,
        title="Human-readable name for the image",
        example="Weekly 2021_34",
    )

    digest: Optional[str] = Field(
        ...,
        title="Hash of the last layer of the Docker container",
        description="May be null if the digest isn't known",
        example=(
            "sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b"
            "01794a30"
        ),
    )

    def __str__(self) -> str:
        return "|".join([self.reference, self.name, self.digest or ""])

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Self:
        return cls(
            reference=data["image_url"],
            name=data["name"],
            digest=data["image_hash"],
        )

    @classmethod
    def from_reference(cls, reference: str) -> Self:
        return cls(
            reference=reference, name=reference.rsplit(":", 1)[1], digest=""
        )


class JupyterConfig(BaseModel):
    """Configuration for talking to JupyterHub and spawning a lab.

    Settings are divided between here and the main BusinessConfig somewhat
    arbitrarily, but the underlying concept is that these settings are used by
    the spawner and API and the settings in BusinessConfig control behavior
    outside of the API calls to JupyterHub.
    """

    url_prefix: str = Field("/nb/", title="URL prefix for Jupyter")

    image_class: JupyterImageClass = Field(
        JupyterImageClass.RECOMMENDED,
        title="How to select the image to spawn",
        description="Only used by JupyterLoginLoop and its subclasses",
    )

    image_reference: Optional[str] = Field(
        None,
        title="Docker reference of lab image to spawn",
        description="Only used if jupyter_image is set to by-reference",
    )

    image_size: str = Field(
        "Large",
        title="Size of image to spawn",
        description="Must be one of the sizes in the nublado2 configuration",
    )

    @validator("image_reference")
    def _valid_image_reference(
        cls, v: str | None, values: dict[str, object]
    ) -> str | None:
        if values.get("image_class") == JupyterImageClass.BY_REFERENCE:
            if not v:
                raise ValueError("image_reference required")
        return v
