"""Models for configuring a Jupyter lab."""

from enum import Enum, auto
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator

__all__ = [
    "JupyterConfig",
    "JupyterImageClass",
    "ControllerImage",
    "ControllerImages",
]


def to_camel_case(string: str) -> str:
    """Convert a string to camel case.

    Originally written for use with Pydantic as an alias generator so that the
    model can be initialized from camel-case input (such as Kubernetes
    objects).

    Parameters
    ----------
    string
        Input string

    Returns
    -------
    str
        String converted to camel-case with the first character in lowercase.
    """
    components = string.split("_")
    return components[0] + "".join(c.title() for c in components[1:])


class CamelCaseModel(BaseModel):
    """This is what we will use in place of BaseModel for the Spawner
    Pydantic models.  Any configuration can be given in Helm-appropriate
    camelCase, but internal Python methods and objects will all be snake_case.

    This isn't actually all that useful here, but since these models are
    copied from jupyterlabcontroller, which *does* make use of these features,
    it's easier than messing with the models.
    """

    class Config:
        """Pydantic configuration."""

        alias_generator = to_camel_case
        allow_population_by_field_name = True


# Dashify is needed to turn, e.g. "latest_weekly" into the required
# "latest-weekly" per sqr-066.  It's also handy for SpawnerEnum.


def dashify(item: str) -> str:
    return item.replace("_", "-")


class SpawnerEnum(str, Enum):
    """This will validate that the name is entirely upper case, and
    will produce auto() values in lower case with underscores turned to
    dashes.
    """

    def _generate_next_value_(  # type: ignore
        name, start, count, last_values
    ) -> str:
        if name != name.upper():
            raise RuntimeError("Enum names must be entirely upper-case")
        return dashify(name.lower())


class NubladoEnum(str, Enum):
    """This will validate that the name is entirely upper case, and
    will produce auto() values in lower case.  This is exactly StrEnum from
    Python 3.11, except for the validation step."""

    def _generate_next_value_(  # type: ignore
        name, start, count, last_values
    ) -> str:
        if name != name.upper():
            raise RuntimeError("Enum names must be entirely upper-case")
        return name.lower()


class PartialImage(CamelCaseModel):
    path: str = Field(
        ...,
        name="path",
        example="lighthouse.ceres/library/sketchbook:latest_daily",
        title="Full Docker registry path for lab image",
        description="cf. https://docs.docker.com/registry/introduction/",
    )
    name: str = Field(
        ...,
        name="name",
        example="Latest Daily (Daily 2077_10_23)",
        title="Human-readable version of image tag",
    )
    digest: str = Field(
        ...,
        name="digest",
        example=(
            "sha256:e693782192ecef4f7846ad2b21"
            "b1574682e700747f94c5a256b5731331a2eec2"
        ),
        title="unique digest of image contents",
    )


class ControllerImage(PartialImage):
    tags: Dict[str, str] = Field(
        ...,
        name="tags",
        title="Map between tag and its display name",
    )
    size: Optional[int] = Field(
        None,
        name="size",
        example=8675309,
        title="Size in bytes of image.  None if image size is unknown",
    )
    prepulled: bool = Field(
        False,
        name="prepulled",
        example=False,
        title="Whether image is prepulled to all eligible nodes",
    )

    @property
    def references(self) -> List[str]:
        r = [f"{self.path}@{self.digest}"]
        for tag in self.tags:
            r.append(f"{self.path}:{tag}")
        return r


class ControllerImages(CamelCaseModel):
    recommended: Optional[ControllerImage] = None
    latest_weekly: Optional[ControllerImage] = None
    latest_daily: Optional[ControllerImage] = None
    latest_release: Optional[ControllerImage] = None
    all: List[ControllerImage] = Field(default_factory=list)

    class Config:
        alias_generator = dashify
        allow_population_by_field_name = True


class JupyterImageClass(SpawnerEnum):
    """Possible ways of selecting an image."""

    RECOMMENDED = auto()
    LATEST_WEEKLY = auto()
    BY_REFERENCE = auto()


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
        cls, v: Optional[str], values: Dict[str, object]
    ) -> Optional[str]:
        if values.get("image_class") == JupyterImageClass.BY_REFERENCE:
            if not v:
                raise ValueError("image_reference required")
        return v
