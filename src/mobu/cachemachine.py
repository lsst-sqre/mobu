"""Client for the cachemachine service."""

from __future__ import annotations

from aiohttp import ClientSession

from .config import config
from .exceptions import CachemachineError
from .models.jupyter import JupyterImage


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
        raise CachemachineError(self._username, "No weekly images found")

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
        if not images or not images[0]:
            raise CachemachineError(self._username, "No images found")
        return images[0]

    async def _get_images(self) -> list[JupyterImage]:
        headers = {"Authorization": f"bearer {self._token}"}
        async with self._session.get(self._url, headers=headers) as r:
            if r.status != 200:
                msg = f"Cannot get image status: {r.status} {r.reason}"
                raise CachemachineError(self._username, msg)
            try:
                data = await r.json()
                return [JupyterImage.from_dict(i) for i in data["images"]]
            except Exception as e:
                msg = f"Invalid response: {type(e).__name__}: {str(e)}"
                raise CachemachineError(self._username, msg)
