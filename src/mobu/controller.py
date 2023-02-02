"""Client for the JupyterLab Controller service."""

from __future__ import annotations

from aiohttp import ClientSession

from .config import config
from .exceptions import ControllerError
from .models.jupyter import ControllerImage, ControllerImages


class ControllerClient:
    """Query the JupyterLab Controller service for image information.

    The JupyterLab Controller is canonical for the available images and
    details such as which image is recommended and what the latest weeklies
    are.  This client queries it and returns the image that matches some
    selection criteria.

    This will be modified into a form suitable for POSTing to the Controller
    to create the requested lab.
    """

    def __init__(
        self, session: ClientSession, token: str, username: str
    ) -> None:
        self._session = session
        self._token = token
        self._username = username
        self._url = config.environment_url + "/nublado/spawner/v1/images"

    async def get_latest_weekly(self) -> ControllerImage:
        """Image for the latest weekly version.

        Returns
        -------
        image : `mobu.models.jupyter.ControllerImage`
            The corresponding image.

        Raises
        ------
        mobu.exceptions.ControllerError
            Some error occurred talking to JupyterLab Controller or it does
            not have a latest weekly image.
        """
        images = await self._get_images()
        if images.latest_weekly is None:
            raise ControllerError(
                self._username, "No latest weekly image found"
            )
        return images.latest_weekly

    async def get_recommended(self) -> ControllerImage:
        """Path suitable for image pulling for the latest recommended version.

        Returns
        -------
        path : `mobu.models.jupyter.ControllerImage`
            The corresponding image.

        Raises
        ------
        mobu.exceptions.ControllerError
            Some error occurred talking to JupyterLab Controller or it does
            not have a recommended image.
        """
        images = await self._get_images()
        if images.recommended is None:
            raise ControllerError(self._username, "No recommended image found")
        return images.recommended

    async def _get_images(self) -> ControllerImages:
        headers = {"Authorization": f"bearer {self._token}"}
        async with self._session.get(self._url, headers=headers) as r:
            if r.status != 200:
                msg = f"Cannot get image status: {r.status} {r.reason}"
                raise ControllerError(self._username, msg)
            try:
                data = await r.json()
                return ControllerImages.parse_obj(data)
            except Exception as e:
                msg = f"Invalid response: {type(e).__name__}: {str(e)}"
                raise ControllerError(self._username, msg)
