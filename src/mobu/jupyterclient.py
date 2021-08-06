"""AsyncIO client for communicating with Jupyter.

Allows the caller to login to the hub, spawn lab containers, and then run
jupyter kernels remotely.
"""

from __future__ import annotations

import json
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import BaseCookie
from typing import TYPE_CHECKING
from uuid import uuid4

from aiohttp import ClientSession, TCPConnector, WSServerHandshakeError

from .config import config
from .exceptions import CodeExecutionError, JupyterError

if TYPE_CHECKING:
    from typing import Any, AsyncIterator, Optional

    from aiohttp import ClientResponse, ClientWebSocketResponse
    from aiohttp.client import _RequestContextManager, _WSRequestContextManager
    from structlog import BoundLogger

    from .models.business import BusinessConfig
    from .models.user import AuthenticatedUser

__all__ = ["JupyterClient", "JupyterLabSession"]

_ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
"""Regex that matches ANSI escape sequences.

See https://stackoverflow.com/questions/14693701/
"""


@dataclass(frozen=True)
class JupyterLabSession:
    """Represents an open session with a Jupyter Lab.

    This holds the information a client needs to talk to the Lab in order to
    execute code.
    """

    session_id: str
    kernel_id: str
    websocket: ClientWebSocketResponse


@dataclass(frozen=True)
class ProgressMessage:
    """A progress message from lab spawning."""

    progress: int
    """Percentage progress on spawning."""

    message: str
    """A progress message."""

    ready: bool
    """Whether the server is ready."""


class JupyterSpawnProgress:
    """Provides status and polling of lab spawn progress.

    This wraps an ongoing call to the progress API, which is an EventStream
    API that provides status messages for a spawning lab.
    """

    def __init__(self, response: ClientResponse, logger: BoundLogger) -> None:
        self._response = response
        self._logger = logger
        self._start = datetime.now(tz=timezone.utc)

    def __aiter__(self) -> AsyncIterator[ProgressMessage]:
        return self.iter()

    async def iter(self) -> AsyncIterator[ProgressMessage]:
        """Iterate over spawn progress events."""
        async for line in self._response.content:
            if not line.startswith(b"data:"):
                continue
            raw_event = line[len(b"data:") :].decode().strip()

            # We have a valid event.  Parse it.
            try:
                event_dict = json.loads(raw_event)
                event = ProgressMessage(
                    progress=event_dict["progress"],
                    message=event_dict["message"],
                    ready=event_dict.get("ready", False),
                )
            except Exception as e:
                msg = f"Ignoring invalid progress event: {raw_event}: {str(e)}"
                self._logger.warning(msg)
                continue

            # Log the event and yield it.
            now = datetime.now(tz=timezone.utc)
            elapsed = int((now - self._start).total_seconds())
            if event.ready:
                status = "complete"
            else:
                status = "in progress"
            msg = f"Spawn {status} ({elapsed}s elapsed): {event.message}"
            self._logger.info(msg)
            yield event


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

    async def close(self) -> None:
        await self.session.close()

    async def hub_login(self) -> None:
        async with self.session.get(self.jupyter_url + "hub/login") as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

    async def lab_login(self) -> None:
        self.log.info("Logging into lab")
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"
        async with self.session.get(lab_url) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

    async def is_lab_stopped(self) -> bool:
        """Determine if the lab is fully stopped."""
        user_url = self.jupyter_url + f"hub/api/users/{self.user.username}"
        headers = {"Referer": self.jupyter_url + "hub/home"}
        async with self.session.get(user_url, headers=headers) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)
            data = await r.json()
        return data["servers"] == {}

    async def is_lab_stopped_obsolete(self) -> bool:
        """Determine if the lab is fully stopped.

        This is the obsolete way of checking if the lab is fully stopped.
        With JupyterHub 1.3 we get 403 permission denied using the API via
        is_lab_stopped, so are falling back to this.  Hopefully this is fixed
        in 1.4.

        Returns
        -------
        is_stopped : `bool`
            `True` if the lab is fully stopped, currently determined by
            whether ``hub/home`` shows a "Start My Server" button, since that
            does not appear to happen until the lab is fully stopped.  `False`
            if it is in any other state, including spawning or stopping.
        """
        home_url = self.jupyter_url + "hub/home"
        async with self.session.get(home_url) as r:
            body = await r.text()
            return re.search(r"Start\s+My\s+Server", body) is not None

    async def spawn_lab(self) -> None:
        spawn_url = self.jupyter_url + "hub/spawn"
        self.log.info(f"Spawning lab for {self.user.username}")

        # Retrieving the spawn page before POSTing to it appears to trigger
        # some necessary internal state construction (and also more accurately
        # simulates a user interaction).  See DM-23864.
        async with self.session.get(spawn_url) as r:
            await r.text()

        # POST the options form to the spawn page.  This should redirect to
        # the spawn-pending page, which will return a 200.
        data = self.jupyter_options_form
        async with self.session.post(spawn_url, data=data) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

    async def spawn_progress(self) -> AsyncIterator[ProgressMessage]:
        """Monitor lab spawn progress.

        This is an EventStream API, which provides a stream of events until
        the lab is spawned or the spawn fails.
        """
        progress_url = (
            self.jupyter_url
            + f"hub/api/users/{self.user.username}/server/progress"
        )
        headers = {"Referer": self.jupyter_url + "hub/home"}
        while True:
            async with self.session.get(progress_url, headers=headers) as r:
                if r.status != 200:
                    raise await JupyterError.from_response(
                        self.user.username, r
                    )
                progress = JupyterSpawnProgress(r, self.log)
                async for message in progress:
                    yield message

            # Sometimes we get only the initial request message and then the
            # progress API immediately closes the connection.  If that
            # happens, try reconnecting to the progress stream after a short
            # delay.
            if message.progress > 0:
                break
            asyncio.sleep(1)
            self.log.info("Retrying spawn progress request")

    async def delete_lab(self) -> None:
        if await self.is_lab_stopped():
            self.log.info("Lab is already stopped")
            return
        user = self.user.username
        server_url = self.jupyter_url + f"hub/api/users/{user}/server"
        headers = {"Referer": self.jupyter_url + "hub/home"}
        async with self.session.delete(server_url, headers=headers) as r:
            if r.status not in [200, 202, 204]:
                raise await JupyterError.from_response(self.user.username, r)

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
                raise await JupyterError.from_response(self.user.username, r)
            response = await r.json()

        kernel_id = response["kernel"]["id"]
        channels_url = (
            self.jupyter_url
            + f"user/{self.user.username}/api/kernels/"
            + f"{kernel_id}/channels"
        )
        try:
            websocket = await self.session.ws_connect(channels_url)
        except WSServerHandshakeError as e:
            raise JupyterError.from_exception(self.user.username, e)
        return JupyterLabSession(
            session_id=response["id"], kernel_id=kernel_id, websocket=websocket
        )

    async def delete_labsession(self, session: JupyterLabSession) -> None:
        user = self.user.username
        session_url = (
            self.jupyter_url + f"user/{user}/api/sessions/{session.session_id}"
        )

        await session.websocket.close()
        async with self.session.delete(session_url) as r:
            if r.status != 204:
                raise await JupyterError.from_response(self.user.username, r)

    async def run_python(self, session: JupyterLabSession, code: str) -> str:
        username = self.user.username
        msg_id = uuid4().hex
        msg = {
            "header": {
                "username": username,
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
            if r.get("parent_header", {}).get("msg_id") != msg_id:
                # Ignore messages not intended for us. The web socket is
                # rather chatty with broadcast status messages.
                continue
            if msg_type == "error":
                error = "".join(r["content"]["traceback"])
                if result:
                    error = result + "\n" + error
                error = self._remove_ansi_escapes(error)
                raise CodeExecutionError(username, code, error=error)
            elif msg_type == "stream":
                result += r["content"]["text"]
            elif msg_type == "execute_reply":
                status = r["content"]["status"]
                if status == "ok":
                    return result
                else:
                    raise CodeExecutionError(username, code, status=status)

    @staticmethod
    def _remove_ansi_escapes(string: str) -> str:
        """Remove ANSI escape sequences from a string.

        Jupyter Lab likes to format error messages with lots of ANSI escape
        sequences, and Slack doesn't like that in messages (nor do humans want
        to see them).  Strip them out.

        See https://stackoverflow.com/questions/14693701/
        """
        return _ANSI_REGEX.sub("", string)
