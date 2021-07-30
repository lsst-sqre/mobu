"""AsyncIO client for communicating with Jupyter.

Allows the caller to login to the hub, spawn lab containers, and then run
jupyter kernels remotely.
"""

from __future__ import annotations

import asyncio
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import BaseCookie
from typing import TYPE_CHECKING
from uuid import uuid4

from aiohttp import ClientResponse, ClientSession, TCPConnector

from .config import config
from .exceptions import LabSpawnTimeoutError, NotebookException

if TYPE_CHECKING:
    from typing import Any, NoReturn, Optional

    from aiohttp import ClientWebSocketResponse
    from aiohttp.client import _RequestContextManager, _WSRequestContextManager
    from structlog import BoundLogger

    from .models.business import BusinessConfig
    from .models.user import AuthenticatedUser

__all__ = ["JupyterClient", "JupyterLabSession"]


@dataclass(frozen=True)
class JupyterLabSession:
    """Represents an open session with a Jupyter Lab.

    This holds the information a client needs to talk to the Lab in order to
    execute code.
    """

    session_id: str
    kernel_id: str
    websocket: ClientWebSocketResponse


class JupyterClientSession:
    """Wrapper around `aiohttp.ClientSession` using token authentication.

    Unfortunately, aioresponses does not capture headers set on the session
    instead of with each individual call, which means that we can't see the
    token and thus determine what user we should interact with in the test
    suite.  Work around this with this wrapper class around
    `aiohttp.ClientSession` that just adds the token header to every call.

    Parameters
    ----------
    session : `aiohttp.ClientSession`
        The session to wrap.
    token : `str`
        The token to send.

    Notes
    -----
    Please do not add any business logic to this class.  It's a workaround for
    https://github.com/pnuckowski/aioresponses/issues/111 and should expose
    exactly the same API as `aiohttp.ClientSesssion` except for the
    constructor.  The goal is to delete it in its entirety and set the
    ``Authorization`` header in the `aiohttp.ClientSession` once that
    aioresponses issue is fixed.
    """

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    async def close(self) -> None:
        await self._session.close()

    def request(
        self, method: str, url: str, **kwargs: Any
    ) -> _RequestContextManager:
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["Authorization"] = f"Bearer {self._token}"
        return self._session.request(method, url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> _RequestContextManager:
        return self.request("delete", url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> _RequestContextManager:
        return self.request("get", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> _RequestContextManager:
        return self.request("post", url, **kwargs)

    def ws_connect(
        self, *args: Any, **kwargs: Any
    ) -> _WSRequestContextManager:
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["Authorization"] = f"Bearer {self._token}"
        return self._session.ws_connect(*args, **kwargs)


class JupyterClient:
    """Client for talking to JupyterHub and Jupyter labs.

    Notes
    -----
    This class creates its own `aiohttp.ClientSession` for each instance,
    separate from the one used by the rest of the application so that it can
    add some custom settings.
    """

    def __init__(
        self,
        user: AuthenticatedUser,
        log: BoundLogger,
        business_config: BusinessConfig,
    ) -> None:
        self.user = user
        self.log = log
        self.jupyter_base = business_config.nb_url
        self.jupyter_url = config.environment_url + self.jupyter_base
        self.jupyter_options_form = business_config.jupyter_options_form

        xsrftoken = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=16)
        )
        headers = {"x-xsrftoken": xsrftoken}
        session = ClientSession(
            headers=headers, connector=TCPConnector(limit=10000)
        )
        session.cookie_jar.update_cookies(BaseCookie({"_xsrf": xsrftoken}))
        self.session = JupyterClientSession(session, user.token)

    __ansi_reg_exp = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")

    @classmethod
    def _ansi_escape(cls, line: str) -> str:
        return cls.__ansi_reg_exp.sub("", line)

    async def close(self) -> None:
        await self.session.close()

    async def hub_login(self) -> None:
        async with self.session.get(self.jupyter_url + "hub/login") as r:
            if r.status != 200:
                await self._raise_error("Error logging into hub", r)

    async def ensure_lab(self) -> None:
        if not await self.lab_has_spawned():
            self.log.info("Lab is not running, spawning")
            await self.spawn_lab()
            self.log.info("Lab created")

    async def lab_login(self) -> None:
        self.log.info("Logging into lab")
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"
        async with self.session.get(lab_url) as r:
            if r.status != 200:
                await self._raise_error("Error logging into lab", r)

    async def lab_is_stopped(self) -> bool:
        """Determine if the lab is fully stopped.

        Returns
        -------
        is_stopped : `bool`
            `True` if the lab is fully stopped, currently determined by
            whether ``hub/home`` shows a "Start My Server" button, since that
            does not appear to happen until the lab is fully stopped.  `False`
            if it is in any other state, including spawning or stopping.

        Notes
        -----
        We have had endless trouble with this interaction with JupyterHub and
        Jupyter Labs, ranging from infinite redirects to false diagnosis of
        the lab as running when it was shutting down.  JupyterHub does not
        appear to provide an API to gather this information, so we're using
        sketchy checks and heuristics that are flawed at best.

        This method should ideally be replaced with an API call as soon as one
        is provided by JupyterHub.
        """
        home_url = self.jupyter_url + "hub/home"
        async with self.session.get(home_url) as r:
            if r.status != 200:
                msg = "Unexpected reply status when seeing if lab is running"
                await self._raise_error(msg, r)
            body = await r.text()
            return re.search(r"Start\s+My\s+Server", body) is not None

    async def lab_has_spawned(self) -> bool:
        """Determine if the lab has finished spawning.

        Returns
        -------
        has_spawned : `bool`
            `True` if the lab has finished spawning, determined by a 200
            response (not a redirect) when going directly to the lab.  `False`
            otherwise.

        Notes
        -----
        As with ``lab_is_stopped``, we've had endless trouble with determining
        this information and have not been able to find a clean API that will
        provide it.  This ideally should be replaced with an API call.
        """
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"

        # If the lab is still spawning, we will get a redirect to the
        # spawn pending page.  If the lab is not running, we will get a
        # redirect to hub/user/<username>/lab, which returns a 503 with a
        # button to start the server.
        async with self.session.get(lab_url) as r:
            if r.status == 200 and lab_url in str(r.url):
                return True
            elif r.status == 503 or "spawn-pending" in str(r.url):
                return False
            else:
                msg = "Unexpected reply when checking if lab spawned"
                await self._raise_error(msg, r)

    async def spawn_lab(self) -> None:
        spawn_url = self.jupyter_url + "hub/spawn"

        # Retrieving the spawn page before POSTing to it appears to trigger
        # some necessary internal state construction (and also more accurately
        # simulates a user interaction).  See DM-23864.
        async with self.session.get(spawn_url) as r:
            await r.text()

        # POST the options form to the spawn page.  This should redirect to
        # the spawn-pending page, which will return a 200.
        data = self.jupyter_options_form
        self.log.info(f"Spawning lab for {self.user.username}")
        async with self.session.post(spawn_url, data=data) as r:
            if r.status != 200:
                msg = "Unexpected reply status after spawning"
                await self._raise_error(msg, r)

        # Poll until the lab has spawned.  Jupyterlab will give up a spawn
        # after 900 seconds, so we shouldn't wait longer than that.
        max_poll_secs = 900
        poll_interval = 15
        retries = max_poll_secs / poll_interval
        start = datetime.now(tz=timezone.utc)
        while retries > 0:
            if await self.lab_has_spawned():
                return
            now = datetime.now(tz=timezone.utc)
            elapsed = int((now - start).total_seconds())
            self.log.info(f"Waiting for lab to spawn ({elapsed}s elapsed)")
            retries -= 1
            await asyncio.sleep(poll_interval)

        # Timed out spawning the lab.
        raise LabSpawnTimeoutError("Lab did not spawn after {max_poll_secs}s")

    async def delete_lab(self) -> None:
        if await self.lab_is_stopped():
            return

        user = self.user.username
        server_url = self.jupyter_url + f"hub/api/users/{user}/server"
        self.log.info(f"Deleting lab for {user}")
        headers = {"Referer": self.jupyter_url + "hub/home"}
        async with self.session.delete(server_url, headers=headers) as r:
            if r.status not in [200, 202, 204]:
                await self._raise_error("Error deleting lab", r)

        # Wait for the lab to actually go away.  If we don't do this, we may
        # try to create a new lab while the old one is still shutting down.
        count = 0
        while not await self.lab_is_stopped() and count < 10:
            self.log.info(f"Waiting for lab deletion ({count}s elapsed)")
            await asyncio.sleep(1)
            count += 1
        if not await self.lab_is_stopped():
            self.log.warning("Giving up on waiting for lab deletion")
        else:
            self.log.info("Lab deleted")

    async def create_labsession(
        self, kernel_name: str = "LSST", notebook_name: Optional[str] = None
    ) -> JupyterLabSession:
        session_url = (
            self.jupyter_url + f"user/{self.user.username}/api/sessions"
        )
        session_type = "notebook" if notebook_name else "console"
        body = {
            "kernel": {"name": kernel_name},
            "name": notebook_name or "(no notebook)",
            "path": uuid4().hex,
            "type": session_type,
        }

        async with self.session.post(session_url, json=body) as r:
            if r.status != 201:
                await self._raise_error("Error creating session", r)
            response = await r.json()

        kernel_id = response["kernel"]["id"]
        return JupyterLabSession(
            session_id=response["id"],
            kernel_id=kernel_id,
            websocket=await self._websocket_connect(kernel_id),
        )

    async def _websocket_connect(
        self, kernel_id: str
    ) -> ClientWebSocketResponse:
        channels_url = (
            self.jupyter_url
            + f"user/{self.user.username}/api/kernels/"
            + f"{kernel_id}/channels"
        )
        self.log.info(f"Opening WebSocket connection at {channels_url}")
        return await self.session.ws_connect(channels_url)

    async def delete_labsession(self, session: JupyterLabSession) -> None:
        user = self.user.username
        session_url = (
            self.jupyter_url + f"user/{user}/api/sessions/{session.session_id}"
        )

        await session.websocket.close()
        async with self.session.delete(session_url) as r:
            if r.status != 204:
                msg = "Unexpected reply status deleting lab session"
                self._raise_error(msg, r)

    async def run_python(self, session: JupyterLabSession, code: str) -> str:
        msg_id = uuid4().hex
        msg = {
            "header": {
                "username": self.user.username,
                "version": "5.0",
                "session": session.session_id,
                "msg_id": msg_id,
                "msg_type": "execute_request",
            },
            "parent_header": {},
            "channel": "shell",
            "content": {
                "code": code,
                "silent": False,
                "store_history": False,
                "user_expressions": {},
                "allow_stdin": False,
            },
            "metadata": {},
            "buffers": {},
        }

        await session.websocket.send_json(msg)

        result = ""
        while True:
            r = await session.websocket.receive_json()
            self.log.debug(f"Recieved kernel message: {r}")
            msg_type = r["msg_type"]
            if r["parent_header"]["msg_id"] != msg_id:
                # Ignore messages not intended for us. The web socket is
                # rather chatty with broadcast status messages.
                continue
            if msg_type == "error":
                error_message = "".join(r["content"]["traceback"])
                raise NotebookException(self._ansi_escape(error_message))
            elif msg_type == "stream":
                result += r["content"]["text"]
            elif msg_type == "execute_reply":
                status = r["content"]["status"]
                if status == "ok":
                    return result
                else:
                    raise NotebookException(f"Result status is {status}")

    async def _raise_error(self, msg: str, r: ClientResponse) -> NoReturn:
        raise Exception(f"{msg}: {r.status} {r.url}: {r.headers}")
