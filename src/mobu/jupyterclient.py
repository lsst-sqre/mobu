"""AsyncIO client for communicating with Jupyter.

Allows the caller to login to the hub, spawn lab containers, and then run
jupyter kernels remotely.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from http.cookies import BaseCookie
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    TypeVar,
    cast,
)
from uuid import uuid4

from aiohttp import (
    ClientResponseError,
    ClientSession,
    TCPConnector,
    WSServerHandshakeError,
)

from .cachemachine import CachemachineClient
from .config import config
from .exceptions import CodeExecutionError, JupyterError, JupyterWebSocketError
from .models.jupyter import JupyterImage, JupyterImageClass

if TYPE_CHECKING:
    from typing import Dict, Optional

    from aiohttp import ClientResponse, ClientWebSocketResponse
    from aiohttp.client import _RequestContextManager, _WSRequestContextManager
    from structlog import BoundLogger

    from .models.jupyter import JupyterConfig
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

    async def __aiter__(self) -> AsyncIterator[ProgressMessage]:
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


# Type of method that can be decorated with _convert_exception.
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
F_Iter = TypeVar("F_Iter", bound=Callable[..., AsyncIterator[Any]])


def _convert_exception(f: F) -> F:
    """Convert web errors to `~mobu.exceptions.JupyterError`."""

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await f(*args, **kwargs)
        except ClientResponseError as e:
            obj = args[0]
            username = obj.user.username
            raise JupyterError.from_exception(username, e) from None

    return cast(F, wrapper)


def _convert_exception_iter(f: F_Iter) -> F_Iter:
    """Convert web errors to `~mobu.exceptions.JupyterError`."""

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            async for r in f(*args, **kwargs):
                yield r
        except ClientResponseError as e:
            obj = args[0]
            username = obj.user.username
            raise JupyterError.from_exception(username, e) from None

    return cast(F_Iter, wrapper)


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
        jupyter_config: JupyterConfig,
    ) -> None:
        self.user = user
        self.log = log
        self.config = jupyter_config
        self.jupyter_url = config.environment_url + jupyter_config.url_prefix

        xsrftoken = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=16)
        )
        headers = {"x-xsrftoken": xsrftoken}
        session = ClientSession(
            headers=headers, connector=TCPConnector(limit=10000)
        )
        session.cookie_jar.update_cookies(BaseCookie({"_xsrf": xsrftoken}))
        self.session = JupyterClientSession(session, user.token)

        # We also send the XSRF token to cachemachine because of how we're
        # sharing the session, but that shouldn't matter.
        assert config.gafaelfawr_token
        self.cachemachine = CachemachineClient(
            session, config.gafaelfawr_token
        )

    async def close(self) -> None:
        await self.session.close()

    @_convert_exception
    async def hub_login(self) -> None:
        async with self.session.get(self.jupyter_url + "hub/login") as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

    @_convert_exception
    async def lab_login(self) -> None:
        self.log.info("Logging into lab")
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"
        async with self.session.get(lab_url) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

    @_convert_exception
    async def is_lab_stopped(self, final: bool = False) -> bool:
        """Determine if the lab is fully stopped.

        Parameters
        ----------
        final : `bool`
            The last attempt, so log some additional information if the lab
            still isn't gone.
        """
        user_url = self.jupyter_url + f"hub/api/users/{self.user.username}"
        headers = {"Referer": self.jupyter_url + "hub/home"}
        async with self.session.get(user_url, headers=headers) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)
            data = await r.json()
        result = data["servers"] == {}
        if final and not result:
            msg = f'Server data still shows running lab: {data["servers"]}'
            self.log.warning(msg)
        return result

    @_convert_exception
    async def spawn_lab(self) -> JupyterImage:
        spawn_url = self.jupyter_url + "hub/spawn"

        # Determine what image to spawn.
        if self.config.image_class == JupyterImageClass.RECOMMENDED:
            image = await self.cachemachine.get_recommended()
        elif self.config.image_class == JupyterImageClass.LATEST_WEEKLY:
            image = await self.cachemachine.get_latest_weekly()
        else:
            assert self.config.image_reference
            image = JupyterImage.from_reference(self.config.image_reference)
        msg = f"Spawning lab image {image.name} for {self.user.username}"
        self.log.info(msg)

        # Retrieving the spawn page before POSTing to it appears to trigger
        # some necessary internal state construction (and also more accurately
        # simulates a user interaction).  See DM-23864.
        async with self.session.get(spawn_url) as r:
            await r.text()

        # POST the options form to the spawn page.  This should redirect to
        # the spawn-pending page, which will return a 200.
        image = await self._get_spawn_image()
        data = self._build_jupyter_spawn_form(image)
        async with self.session.post(spawn_url, data=data) as r:
            if r.status != 200:
                raise await JupyterError.from_response(self.user.username, r)

        # Return information about the image spawned so that we can use it to
        # annotate timers and get it into error reports.
        return image

    @_convert_exception_iter
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
            await asyncio.sleep(1)
            self.log.info("Retrying spawn progress request")

    @_convert_exception
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

    @_convert_exception
    async def create_labsession(
        self, notebook_name: Optional[str] = None, *, kernel_name: str = "LSST"
    ) -> JupyterLabSession:
        session_url = (
            self.jupyter_url + f"user/{self.user.username}/api/sessions"
        )
        session_type = "notebook" if notebook_name else "console"
        body = {
            "kernel": {"name": kernel_name},
            "name": notebook_name or "(no notebook)",
            "path": notebook_name if notebook_name else uuid4().hex,
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
            websocket = await self.session.ws_connect(
                channels_url, max_msg_size=0
            )
        except WSServerHandshakeError as e:
            raise JupyterError.from_exception(self.user.username, e) from None
        return JupyterLabSession(
            session_id=response["id"], kernel_id=kernel_id, websocket=websocket
        )

    @_convert_exception
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
            try:
                r = await session.websocket.receive_json()
            except TypeError as e:
                # The aiohttp WebSocket code raises the unhelpful error
                # message TypeError("Received message 257:None is not str")
                # if the WebSocket connection is abruptly closed.  Translate
                # this into a useful error that we can annotate.
                if "Received message 257" in str(e):
                    error = "WebSocket unexpectedly closed"
                    raise JupyterWebSocketError(username, error) from e
                else:
                    raise

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

    def _build_jupyter_spawn_form(self, image: JupyterImage) -> Dict[str, str]:
        """Construct the form to submit to the JupyterHub login page."""
        return {
            "image_list": str(image),
            "image_dropdown": "use_image_from_dropdown",
            "size": self.config.image_size,
        }

    async def _get_spawn_image(self) -> JupyterImage:
        """Determine what image to spawn."""
        if self.config.image_class == JupyterImageClass.RECOMMENDED:
            return await self.cachemachine.get_recommended()
        elif self.config.image_class == JupyterImageClass.LATEST_WEEKLY:
            return await self.cachemachine.get_latest_weekly()
        elif self.config.image_class == JupyterImageClass.BY_REFERENCE:
            assert self.config.image_reference
            return JupyterImage.from_reference(self.config.image_reference)
        else:
            # This should be prevented by the model as long as we don't add a
            # new image class without adding the corresponding condition.
            raise ValueError(f"Invalid image_class {self.config.image_class}")
