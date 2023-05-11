"""AsyncIO client for communicating with Jupyter.

Allows the caller to login to the hub, spawn lab containers, and then run
jupyter kernels remotely.
"""

from __future__ import annotations

import asyncio
import random
import string
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from functools import wraps
from types import TracebackType
from typing import (
    Any,
    Concatenate,
    Literal,
    Optional,
    ParamSpec,
    Self,
    TypeVar,
)
from urllib.parse import urlparse
from uuid import uuid4

from httpx import AsyncClient, HTTPError
from httpx_sse import EventSource, aconnect_sse
from httpx_ws import AsyncWebSocketSession, HTTPXWSException, aconnect_ws
from safir.datetime import current_datetime
from structlog.stdlib import BoundLogger

from ..config import config
from ..exceptions import (
    CodeExecutionError,
    JupyterWebError,
    JupyterWebSocketError,
)
from ..models.business.nublado import (
    NubladoImage,
    NubladoImageByClass,
    NubladoImageByReference,
    NubladoImageClass,
)
from ..models.user import AuthenticatedUser
from .cachemachine import CachemachineClient, JupyterCachemachineImage

P = ParamSpec("P")
T = TypeVar("T")

__all__ = ["JupyterClient", "JupyterLabSession"]


@dataclass(frozen=True, slots=True)
class SpawnProgressMessage:
    """A progress message from lab spawning."""

    progress: int
    """Percentage progress on spawning."""

    message: str
    """A progress message."""

    ready: bool
    """Whether the server is ready."""


class JupyterSpawnProgress:
    """Provides status and polling of lab spawn progress.

    This parses messages from the progress API, which is an EventStream API
    that provides status messages for a spawning lab.

    Parameters
    ----------
    event_source
        Open EventStream connection.
    logger
        Logger to use.
    """

    def __init__(self, event_source: EventSource, logger: BoundLogger) -> None:
        self._source = event_source
        self._logger = logger
        self._start = current_datetime(microseconds=True)

    async def __aiter__(self) -> AsyncIterator[SpawnProgressMessage]:
        """Iterate over spawn progress events.

        Yields
        ------
        SpawnProgressMessage
            The next progress message.

        Raises
        ------
        httpx.HTTPError
            Raised if a protocol error occurred while connecting to the
            EventStream API or reading or parsing a message from it.
        """
        async for sse in self._source.aiter_sse():
            try:
                event_dict = sse.json()
                event = SpawnProgressMessage(
                    progress=event_dict["progress"],
                    message=event_dict["message"],
                    ready=event_dict.get("ready", False),
                )
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)}"
                msg = f"Error parsing progress event, ignoring: {err}"
                self._logger.warning(msg, type=sse.event, data=sse.data)
                continue

            # Log the event and yield it.
            now = current_datetime(microseconds=True)
            elapsed = int((now - self._start).total_seconds())
            if event.ready:
                status = "complete"
            else:
                status = "in progress"
            msg = f"Spawn {status} ({elapsed}s elapsed): {event.message}"
            self._logger.info(msg)
            yield event


@dataclass(frozen=True, slots=True)
class JupyterOutput:
    """Output from a Jupyter lab kernel.

    Parsing WebSocket messages will result in a stream of these objects with
    partial output, ending in a final one with the ``done`` flag set.
    """

    content: str
    """Partial output from code execution (may be empty)."""

    done: bool = False
    """Whether this indicates the end of execution."""


class JupyterLabSession:
    """Represents an open session with a Jupyter Lab.

    A context manager providing an open WebSocket session. The session will be
    automatically deleted when exiting the context manager. Objects of this
    type should be created by calling `JupyterClient.open_lab_session`.

    Parameters
    ----------
    username
        User the session is for.
    session_id
        Identifier of the Jupyter lab session, which must be created before
        creating this session.
    websocket_url
        URL on which to create a WebSocket session.
    close_url
        URL to which to send a DELETE to close the lab session.
    client
        HTTP client to talk to the Jupyter lab.
    logger
        Logger to use.
    """

    def __init__(
        self,
        *,
        username: str,
        session_id: str,
        websocket_url: str,
        close_url: str,
        client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        self._username = username
        self._session_id = session_id
        self._websocket_url = websocket_url
        self._close_url = close_url
        self._client = client
        self._logger = logger
        self._socket: Optional[AsyncWebSocketSession] = None

    async def __aenter__(self) -> Self:
        url = self._websocket_url
        try:
            self._socket = await aconnect_ws(url, self._client).__aenter__()
        except HTTPXWSException as e:
            user = self._username
            raise JupyterWebSocketError.from_exception(e, user) from e
        return self

    async def __aexit__(
        self,
        exc_type: type[Exception] | None,
        exc_val: Exception | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        try:
            r = await self._client.delete(self._close_url)
            r.raise_for_status()
        except HTTPError as e:
            # Be careful to not raise an exception if we're already processing
            # an exception, since the exception from inside the context
            # manager is almost certainly more interesting than the exception
            # from closing the lab session.
            if exc_type:
                self._logger.exception("Failed to close session")
            else:
                raise JupyterWebError.from_exception(e, self._username) from e
        return False

    async def run_python(self, code: str) -> str:
        """Run a block of Python code in a Jupyter lab kernel.

        Parameters
        ----------
        code
            Code to run.

        Returns
        -------
        str
            Output from the kernel.

        Raises
        ------
        JupyterCodeExecutionError
            Raised if an error was reported by the Jupyter lab kernel.
        JupyterWebSocketError
            Raised if there was a WebSocket protocol error while running code
            or waiting for the response.
        RuntimeError
            Raised if called before entering the context and thus before
            creating the WebSocket session.
        """
        if not self._socket:
            raise RuntimeError("JupyterLabSession not opened")
        message_id = uuid4().hex
        message = {
            "header": {
                "username": self._username,
                "version": "5.0",
                "session": self._session_id,
                "msg_id": message_id,
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
        await self._socket.send_json(message)

        # Consume messages waiting for the response.
        result = ""
        while True:
            try:
                message = await self._socket.receive_json()
            except HTTPXWSException as e:
                user = self._username
                raise JupyterWebSocketError.from_exception(e, user) from e
            self._logger.debug("Received kernel message", message=message)

            # Parse the received message.
            try:
                output = self._parse_message(message, message_id)
            except CodeExecutionError as e:
                e.code = code
                raise
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)}"
                msg = "Ignoring unparsable web socket message"
                self._logger.warning(msg, error=error, message=message)

            # Accumulate the results if they are of interest, and exit and
            # return the results if this message indicated the end of
            # execution.
            if not output:
                continue
            result += output.content
            if output.done:
                break

        # Return the accumulated output.
        return result

    def _parse_message(
        self, message: dict[str, Any], message_id: str
    ) -> JupyterOutput | None:
        """Parse a WebSocket message from a Jupyter lab kernel.

        Parameters
        ----------
        message
            Raw message decoded from JSON.
        message_id
            Identifier of message we sent, used to ignore messages that aren't
            in response to our message.

        Returns
        -------
        JupyterOutput or None
            Parsed message, or `None` if the message wasn't of interest.

        Raises
        ------
        KeyError
            Raised if the WebSocket message wasn't in the expected format.
        """
        msg_type = message["msg_type"]

        # Ignore headers not intended for us. Thie web socket is rather
        # chatty with broadcast status messages.
        if message.get("parent_header", {}).get("msg_id") != message_id:
            return None

        # Analyse the message type to figure out what to do with the response.
        if msg_type in ("execute_input", "status"):
            return None
        elif msg_type == "stream":
            return JupyterOutput(content=message["content"]["text"])
        elif msg_type == "execute_reply":
            status = message["content"]["status"]
            if status == "ok":
                return JupyterOutput(content="", done=True)
            else:
                raise CodeExecutionError(user=self._username, status=status)
        elif msg_type == "error":
            error = "".join(message["content"]["traceback"])
            raise CodeExecutionError(user=self._username, error=error)
        else:
            msg = "Ignoring unrecognized WebSocket message"
            self._logger.warning(msg, message_type=msg_type, message=message)
            return None


def _convert_exception(
    f: Callable[Concatenate[JupyterClient, P], Coroutine[None, None, T]]
) -> Callable[Concatenate[JupyterClient, P], Coroutine[None, None, T]]:
    """Convert web errors to a `~mobu.exceptions.JupyterWebError`.

    This can only be used as a decorator on `JupyterClientSession` or another
    object that has a ``user`` property containing an
    `~mobu.models.user.AuthenticatedUser`.
    """

    @wraps(f)
    async def wrapper(
        client: JupyterClient, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        try:
            return await f(client, *args, **kwargs)
        except HTTPError as e:
            username = client.user.username
            raise JupyterWebError.from_exception(e, username) from e

    return wrapper


def _convert_iterator_exception(
    f: Callable[Concatenate[JupyterClient, P], AsyncIterator[T]]
) -> Callable[Concatenate[JupyterClient, P], AsyncIterator[T]]:
    """Convert web errors to a `~mobu.exceptions.JupyterWebError`.

    This can only be used as a decorator on `JupyterClientSession` or another
    object that has a ``user`` property containing an
    `~mobu.models.user.AuthenticatedUser`.
    """

    @wraps(f)
    async def wrapper(
        client: JupyterClient, *args: P.args, **kwargs: P.kwargs
    ) -> AsyncIterator[T]:
        try:
            async for result in f(client, *args, **kwargs):
                yield result
        except HTTPError as e:
            username = client.user.username
            raise JupyterWebError.from_exception(e, username) from e

    return wrapper


class JupyterClient:
    """Client for talking to JupyterHub and Jupyter labs.

    Parameters
    ----------
    user
        User as which to authenticate.
    url_prefix
        URL prefix to talk to JupyterHub.
    image_config
        Specification for image to request when spawning.
    logger
        Logger to use.

    Notes
    -----
    This class creates its own `httpx.AsyncClient` for each instance, separate
    from the one used by the rest of the application, since it needs to
    isolate the cookies set by JupyterHub and the lab from those for any other
    user.
    """

    def __init__(
        self,
        *,
        user: AuthenticatedUser,
        url_prefix: str,
        image_config: NubladoImage,
        logger: BoundLogger,
    ) -> None:
        self.user = user
        self._logger = logger.bind(user=user.username)
        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        self._config = image_config
        base_url = str(config.environment_url).rstrip("/")
        self._jupyter_url = base_url + url_prefix

        # Construct a connection pool to use for requets to JupyterHub. We
        # have to create a separate connection pool for every monkey, since
        # each will get user-specific cookies set by JupyterHub. If we shared
        # connection pools, monkeys would overwrite each other's cookies and
        # get authentication failures from labs.
        #
        # Add the XSRF token used by JupyterHub to the headers and cookie.
        # Ideally we would use whatever path causes these to be set in a
        # normal browser, but I haven't figured that out.
        alphabet = string.ascii_uppercase + string.digits
        xsrf_token = "".join(random.choices(alphabet, k=16))
        headers = {
            "Authorization": f"Bearer {user.token}",
            "X-XSRFToken": xsrf_token,
        }
        cookies = {"_xsrf": xsrf_token}
        self._client = AsyncClient(
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
            timeout=30.0,  # default is 5, but JupyterHub can be slow
        )

        # Use the same client to talk to cachemachine. This means we'll send
        # the same headers and cookies there, but that won't matter (the
        # header gets overridden), and cachemachine support is soon going away
        # so it's not worth a lot of effort.
        self._cachemachine = None
        if config.use_cachemachine:
            if not config.gafaelfawr_token:
                raise RuntimeError("GAFAELFAWR_TOKEN not set")
            self._cachemachine = CachemachineClient(
                self._client, config.gafaelfawr_token, self.user.username
            )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    @_convert_exception
    async def auth_to_hub(self) -> None:
        """Retrieve the JupyterHub home page.

        This forces a refresh of the authentication cookies set in the client
        session, which may be required to use API calls that return 401 errors
        instead of redirecting the user to log in.
        """
        url = self._url_for("hub/home")
        r = await self._client.get(url)
        r.raise_for_status()

    @_convert_exception
    async def auth_to_lab(self) -> None:
        """Authenticate to the Jupyter lab.

        Request the top-level lab page, which will force the OpenID Connect
        authentication with JupyterHub and set authentication cookies. This is
        required before making API calls to the lab, such as running code.
        """
        url = self._url_for(f"user/{self.user.username}/lab")
        r = await self._client.get(url)
        r.raise_for_status()

    @_convert_exception
    async def is_lab_stopped(self, log_running: bool = False) -> bool:
        """Determine if the lab is fully stopped.

        Parameters
        ----------
        log_running
            Log a warning with additional information if the lab still
            exists.
        """
        url = self._url_for(f"hub/api/users/{self.user.username}")
        headers = {"Referer": self._url_for("hub/home")}
        r = await self._client.get(url, headers=headers)
        r.raise_for_status()

        # We currently only support a single lab per user, so the lab is
        # running if and only if the server data for the user is not empty.
        data = r.json()
        result = data["servers"] == {}
        if log_running and not result:
            msg = "User API data still shows running lab"
            self._logger.warning(msg, servers=data["servers"])
        return result

    @_convert_exception
    async def open_lab_session(
        self, notebook_name: Optional[str] = None, *, kernel_name: str = "LSST"
    ) -> JupyterLabSession:
        """Open a Jupyter lab session.

        Returns a context manager object so must be called via ``async with``
        or the equivalent. The lab session will automatically be deleted when
        the context manager exits.

        Parameters
        ----------
        nobebook_name
            Name of the notebook we will be running, which is passed to the
            session and might influence logging on the lab side. If set, the
            session type will be set to ``notebook``. If not set, the session
            type will be set to ``console``.
        kernel_name
            Name of the kernel to use for the session.

        Returns
        -------
        JupyterLabSession
            Context manager to open the WebSocket session.
        """
        username = self.user.username
        url = self._url_for(f"user/{username}/api/sessions")
        body = {
            "kernel": {"name": kernel_name},
            "name": notebook_name or "(no notebook)",
            "path": notebook_name if notebook_name else uuid4().hex,
            "type": "notebook" if notebook_name else "console",
        }
        r = await self._client.post(url, json=body)
        r.raise_for_status()
        response = r.json()
        session_id = response["id"]
        kernel_id = response["kernel"]["id"]
        close_url = self._url_for(f"user/{username}/api/sessions/{session_id}")
        return JupyterLabSession(
            username=username,
            websocket_url=self._url_for_lab_websocket(username, kernel_id),
            close_url=close_url,
            session_id=session_id,
            client=self._client,
            logger=self._logger,
        )

    @_convert_exception
    async def spawn_lab(self) -> None:
        """Spawn a Jupyter lab pod."""
        url = self._url_for("hub/spawn")
        data = await self._build_spawn_form()

        # Retrieving the spawn page before POSTing to it appears to trigger
        # some necessary internal state construction (and also more accurately
        # simulates a user interaction). See DM-23864.
        r = await self._client.get(url)
        r.raise_for_status()

        # POST the options form to the spawn page. This should redirect to
        # the spawn-pending page, which will return a 200.
        self._logger.info("Spawning lab image", user=self.user.username)
        r = await self._client.post(url, data=data)
        r.raise_for_status()

    @_convert_exception
    async def stop_lab(self) -> None:
        """Stop the user's Jupyter lab."""
        if await self.is_lab_stopped():
            self._logger.info("Lab is already stopped")
            return
        url = self._url_for(f"hub/api/users/{self.user.username}/server")
        headers = {"Referer": self._url_for("hub/home")}
        r = await self._client.delete(url, headers=headers)
        r.raise_for_status()

    @_convert_iterator_exception
    async def watch_spawn_progress(
        self,
    ) -> AsyncIterator[SpawnProgressMessage]:
        """Monitor lab spawn progress.

        This is an EventStream API, which provides a stream of events until
        the lab is spawned or the spawn fails.

        Yields
        ------
        SpawnProgressMessage
            Next progress message from JupyterHub.
        """
        client = self._client
        username = self.user.username
        url = self._url_for(f"hub/api/users/{username}/server/progress")
        headers = {"Referer": self._url_for("hub/home")}
        while True:
            async with aconnect_sse(client, "GET", url, headers=headers) as s:
                async for message in JupyterSpawnProgress(s, self._logger):
                    yield message

            # Sometimes we get only the initial request message and then the
            # progress API immediately closes the connection. If that happens,
            # try reconnecting to the progress stream after a short delay.  I
            # beleive this was a bug in kubespawner, so once we've switched to
            # the lab controller everywhere, we can probably drop this code.
            if message.progress > 0:
                break
            await asyncio.sleep(1)
            self._logger.info("Retrying spawn progress request")

    async def _build_spawn_form(self) -> dict[str, str]:
        """Construct the form data to post to JupyterHub's spawn form."""
        if self._cachemachine:
            image_class = self._config.image_class
            if isinstance(self._config, NubladoImageByClass):
                if image_class == NubladoImageClass.RECOMMENDED:
                    image = await self._cachemachine.get_recommended()
                elif image_class == NubladoImageClass.LATEST_WEEKLY:
                    image = await self._cachemachine.get_latest_weekly()
                else:
                    msg = f"Unsupported image class {image_class}"
                    raise ValueError(msg)
            elif isinstance(self._config, NubladoImageByReference):
                reference = self._config.reference
                image = JupyterCachemachineImage.from_reference(reference)
            else:
                msg = f"Unsupported image class {image_class}"
                raise ValueError(msg)
            return self._build_spawn_form_from_cachemachine(image)
        else:
            return self._config.to_spawn_form()

    def _build_spawn_form_from_cachemachine(
        self, image: JupyterCachemachineImage
    ) -> dict[str, str]:
        """Construct the form to submit to the JupyterHub login page."""
        return {
            "image_list": str(image),
            "image_dropdown": "use_image_from_dropdown",
            "size": self._config.size.value,
        }

    def _url_for(self, partial: str) -> str:
        """Construct a JupyterHub or Jupyter lab URL from a partial URL.

        Parameters
        ----------
        partial
            Part of the URL after the prefix for JupyterHub.

        Returns
        -------
        str
            Full URL to use.
        """
        if self._jupyter_url.endswith("/"):
            return f"{self._jupyter_url}{partial}"
        else:
            return f"{self._jupyter_url}/{partial}"

    def _url_for_lab_websocket(self, username: str, kernel: str) -> str:
        """Build the URL for the WebSocket to a lab kernel."""
        url = self._url_for(f"user/{username}/api/kernels/{kernel}/channels")
        return urlparse(url)._replace(scheme="wss").geturl()
