"""Client for the cachemachine service."""

from __future__ import annotations

from typing import Self

from httpx import AsyncClient, HTTPError, HTTPStatusError
from pydantic import BaseModel, Field

from ..exceptions import CachemachineError
from ..models.business.nublado import CachemachinePolicy

__all__ = [
    "CachemachineClient",
    "JupyterCachemachineImage",
]


class JupyterCachemachineImage(BaseModel):
    """Represents an image to spawn as a Jupyter Lab."""

    reference: str = Field(
        ...,
        title="Docker reference for the image",
        examples=["registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_13"],
    )

    name: str = Field(
        ...,
        title="Human-readable name for the image",
        examples=["Weekly 2021_34"],
    )

    digest: str | None = Field(
        ...,
        title="Hash of the last layer of the Docker container",
        description="May be null if the digest isn't known",
        examples=[
            "sha256:419c4b7e14603711b25fa9e0569460a753c4b2449fe275bb5f89743b"
            "01794a30"
        ],
    )

    def __str__(self) -> str:
        return "|".join([self.reference, self.name, self.digest or ""])

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Self:
        """Convert from the cachemachine API reply.

        Paramaters
        ----------
        data
            Image data from cachemachine.

        Returns
        -------
        JupyterCachemachineImage
            Corresponding image.
        """
        return cls(
            reference=data["image_url"],
            name=data["name"],
            digest=data["image_hash"],
        )

    @classmethod
    def from_reference(cls, reference: str) -> Self:
        """Convert from a Docker reference.

        Parameters
        ----------
        reference
            Docker reference for an image.

        Returns
        -------
        JupyterCachemachineImage
            Corresponding image.
        """
        return cls(
            reference=reference, name=reference.rsplit(":", 1)[1], digest=""
        )


class CachemachineClient:
    """Query the cachemachine service for image information.

    Cachemachine is canonical for the available images and details such as
    which image is recommended and what the latest weeklies are.  This client
    queries it and returns the image that matches some selection criteria.
    The resulting string can be passed in to the JupyterHub options form.

    Parameters
    ----------
    url
        URL for cachemachine.
    token
        Token to use to authenticate to cachemachine.
    http_client
        HTTP client to use.
    image_policy
        Cachemachine image policy to use for resolving images.
    """

    def __init__(
        self,
        url: str,
        token: str,
        http_client: AsyncClient,
        *,
        image_policy: CachemachinePolicy = CachemachinePolicy.desired,
    ) -> None:
        self._token = token
        self._http_client = http_client
        self._url = url.rstrip("/") + "/" + image_policy.value

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
        raise CachemachineError("No weekly images found")

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
            raise CachemachineError("No images found")
        return images[0]

    async def _get_images(self) -> list[JupyterCachemachineImage]:
        headers = {"Authorization": f"bearer {self._token}"}
        try:
            r = await self._http_client.get(self._url, headers=headers)
            r.raise_for_status()
        except HTTPStatusError as e:
            msg = f"Cannot get image status: {e.response.status_code}"
            raise CachemachineError(msg) from e
        except HTTPError as e:
            msg = f"Cannot get image status: {type(e).__name__}: {e!s}"
            raise CachemachineError(msg) from e

        try:
            data = r.json()
            return [
                JupyterCachemachineImage.from_dict(i) for i in data["images"]
            ]
        except Exception as e:
            msg = f"Invalid response: {type(e).__name__}: {e!s}"
            raise CachemachineError(msg) from e
