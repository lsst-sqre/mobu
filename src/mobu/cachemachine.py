"""Client for the cachemachine service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from .config import config
from .exceptions import CachemachineError
from .models.jupyter import JupyterImage

if TYPE_CHECKING:
    from typing import List

    from aiohttp import ClientSession


class CachemachineClient:
    """Query the cachemachine service for image information.

    Cachemachine is canonical for the available images and details such as
    which image is recommended and what the latest weeklies are.  This client
    queries it and returns the image that matches some selection criteria.
    The resulting string can be passed in to the JupyterHub options form.
    """

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._url = urljoin(
            config.environment_url, "cachemachine/jupyter/available"
        )

    async def get_latest_weekly(self) -> JupyterImage:
        """Image for the latest weekly version.

        Returns
        -------
        image : `mobu.models.jupyter.JupyterImage`
            The corresponding image.

        Raises
        ------
        mobu.exceptions.CachemachineError
            Some error occurred talking to cachemachine or cachemachine does
            not have any weekly images.
        """
        for image in await self._get_images():
            if image.name.startswith("Weekly"):
                return image
        raise CachemachineError("No weekly versions found")

    async def get_recommended(self) -> JupyterImage:
        """Image string for the latest recommended version.

        Returns
        -------
        image : `mobu.models.jupyter.JupyterImage`
            The corresponding image.

        Raises
        ------
        mobu.exceptions.CachemachineError
            Some error occurred talking to cachemachine.
        """
        images = await self._get_images()
        return images[0]

    async def _get_images(self) -> List[JupyterImage]:
        headers = {"Authorization": f"bearer {self._token}"}
        async with self._session.get(self._url, headers=headers) as r:
            if r.status != 200:
                msg = (
                    "Cannot get image status from cachemachine: "
                    f"{r.status} {r.reason}"
                )
                raise CachemachineError(msg)
            try:
                data = await r.json()
                return [JupyterImage.from_dict(i) for i in data["images"]]
            except Exception as e:
                msg = f"Invalid response from cachemachine: {str(e)}"
                raise CachemachineError(msg)
