"""Client for the cachemachine service."""

from __future__ import annotations

from typing import Optional, Self

from aiohttp import ClientSession
from pydantic import BaseModel, Field

from ..config import config
from ..exceptions import CachemachineError


class JupyterCachemachineImage(BaseModel):
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


class CachemachineClient:
    """Query the cachemachine service for image information.

    Cachemachine is canonical for the available images and details such as
    which image is recommended and what the latest weeklies are.  This client
    queries it and returns the image that matches some selection criteria.
    The resulting string can be passed in to the JupyterHub options form.
    """

    def __init__(
        self, session: ClientSession, token: str, username: str
    ) -> None:
        self._session = session
        self._token = token
        self._username = username
        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        self._url = (
            str(config.environment_url).rstrip("/")
            + "/cachemachine/jupyter/"
            + config.cachemachine_image_policy.value
        )

    async def get_latest_weekly(self) -> JupyterCachemachineImage:
        """Image for the latest weekly version.

        Returns
        -------
        JupyterCachemachineImage
            Corresponding image.

        Raises
        ------
        CachemachineError
            Some error occurred talking to cachemachine or cachemachine does
            not have any weekly images.
        """
        for image in await self._get_images():
            if image.name.startswith("Weekly"):
                return image
        raise CachemachineError(self._username, "No weekly images found")

    async def get_recommended(self) -> JupyterCachemachineImage:
        """Image string for the latest recommended version.

        Returns
        -------
        JupyterCachemachineImage
            Corresponding image.

        Raises
        ------
        CachemachineError
            Some error occurred talking to cachemachine.
        """
        images = await self._get_images()
        if not images or not images[0]:
            raise CachemachineError(self._username, "No images found")
        return images[0]

    async def _get_images(self) -> list[JupyterCachemachineImage]:
        headers = {"Authorization": f"bearer {self._token}"}
        async with self._session.get(self._url, headers=headers) as r:
            if r.status != 200:
                msg = f"Cannot get image status: {r.status} {r.reason}"
                raise CachemachineError(self._username, msg)
            try:
                data = await r.json()
                return [
                    JupyterCachemachineImage.from_dict(i)
                    for i in data["images"]
                ]
            except Exception as e:
                msg = f"Invalid response: {type(e).__name__}: {str(e)}"
                raise CachemachineError(self._username, msg)
