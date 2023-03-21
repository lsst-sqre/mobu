"""A mock JupyterHub/Lab for tests."""

from __future__ import annotations

import asyncio
import json
import re
from base64 import urlsafe_b64decode
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from enum import Enum
from io import StringIO
from re import Pattern
from traceback import format_exc
from typing import Any, Optional
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from aiohttp import ClientWebSocketResponse, RequestInfo, TooManyRedirects
from aioresponses import CallbackResult, aioresponses
from multidict import CIMultiDict, CIMultiDictProxy
from safir.datetime import current_datetime
from yarl import URL

from mobu.config import config
from mobu.services.business.nublado import _GET_NODE
from mobu.storage.jupyter import JupyterLabSession


class JupyterAction(Enum):
    LOGIN = "login"
    HOME = "home"
    HUB = "hub"
    USER = "user"
    PROGRESS = "progress"
    SPAWN = "spawn"
    SPAWN_PENDING = "spawn_pending"
    LAB = "lab"
    DELETE_LAB = "delete_lab"
    CREATE_SESSION = "create_session"
    DELETE_SESSION = "delete_session"


class JupyterState(Enum):
    LOGGED_OUT = "logged out"
    LOGGED_IN = "logged in"
    SPAWN_PENDING = "spawn pending"
    LAB_RUNNING = "lab running"


def _url(route: str, regex: bool = False) -> str | Pattern[str]:
    """Construct a URL for JupyterHub/Proxy."""
    base_url = str(config.environment_url).rstrip("/")
    if not regex:
        return f"{base_url}/nb/{route}"

    prefix = re.escape(f"{base_url}/nb/")
    return re.compile(prefix + route)


class MockJupyter:
    """A mock Jupyter state machine.

    This should be invoked via mocked HTTP calls so that tests can simulate
    making REST calls to the real JupyterHub/Lab.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, JupyterLabSession] = {}
        self.state: dict[str, JupyterState] = {}
        self.delete_immediate = True
        self.spawn_timeout = False
        self.redirect_loop = False
        self._delete_at: dict[str, datetime | None] = {}
        self._fail: dict[str, dict[JupyterAction, bool]] = {}

    def fail(self, user: str, action: JupyterAction) -> None:
        """Configure the given action to fail for the given user."""
        if user not in self._fail:
            self._fail[user] = {}
        self._fail[user][action] = True

    def login(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.LOGIN in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LOGGED_OUT:
            self.state[user] = JupyterState.LOGGED_IN
        return CallbackResult(status=200)

    def user(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.USER in self._fail.get(user, {}):
            return CallbackResult(status=500)
        assert str(url).endswith(f"/hub/api/users/{user}")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.SPAWN_PENDING:
            server = {"name": "", "pending": "spawn", "ready": False}
            body = {"name": user, "servers": {"": server}}
        elif state == JupyterState.LAB_RUNNING:
            delete_at = self._delete_at.get(user)
            if delete_at and current_datetime(microseconds=True) > delete_at:
                del self._delete_at[user]
                self.state[user] = JupyterState.LOGGED_IN
            if delete_at:
                server = {"name": "", "pending": "delete", "ready": False}
            else:
                server = {"name": "", "pending": None, "ready": True}
            body = {"name": user, "servers": {"": server}}
        else:
            body = {"name": user, "servers": {}}
        return CallbackResult(status=200, body=json.dumps(body))

    async def progress(self, url: URL, **kwargs: Any) -> CallbackResult:
        if self.redirect_loop:
            headers: CIMultiDict[str] = CIMultiDict()
            raise TooManyRedirects(
                request_info=RequestInfo(
                    url=url,
                    method="GET",
                    headers=CIMultiDictProxy(headers),
                    real_url=url,
                ),
                history=(),
                status=303,
            )
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/api/users/{user}/server/progress")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state in (JupyterState.SPAWN_PENDING, JupyterState.LAB_RUNNING)
        if JupyterAction.PROGRESS in self._fail.get(user, {}):
            body = (
                'data: {"progress": 0, "message": "Server requested"}\n'
                'data: {"progress": 50, "message": "Spawning server..."}\n'
                'data: {"progress": 75, "message": "Spawn failed!"}\n'
            )
        elif state == JupyterState.LAB_RUNNING:
            body = (
                'data: {"progress": 100, "ready": true, "message": "Ready"}\n'
            )
        elif self.spawn_timeout:
            # Cause the spawn to time out by pausing for longer than the test
            # should run for and then returning nothing.
            await asyncio.sleep(60)
            body = ""
        else:
            self.state[user] = JupyterState.LAB_RUNNING
            body = (
                'data: {"progress": 0, "message": "Server requested"}\n'
                'data: {"progress": 50, "message": "Spawning server..."}\n'
                'data: {"progress": 100, "ready": true, "message": "Ready"}\n'
            )
        return CallbackResult(status=200, body=body)

    def spawn(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.SPAWN in self._fail.get(user, {}):
            return CallbackResult(status=500, method="POST", reason="foo")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LOGGED_IN
        self.state[user] = JupyterState.SPAWN_PENDING
        return CallbackResult(
            status=302,
            headers={"Location": _url(f"hub/spawn-pending/{user}")},
        )

    def spawn_pending(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/spawn-pending/{user}")
        if JupyterAction.SPAWN_PENDING in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.SPAWN_PENDING
        return CallbackResult(status=200)

    def missing_lab(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/user/{user}/lab")
        return CallbackResult(status=503)

    def lab(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/user/{user}/lab")
        if JupyterAction.LAB in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LAB_RUNNING:
            return CallbackResult(status=200)
        else:
            return CallbackResult(
                status=302, headers={"Location": _url(f"hub/user/{user}/lab")}
            )

    def delete_lab(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/users/{user}/server")
        if JupyterAction.DELETE_LAB in self._fail.get(user, {}):
            return CallbackResult(status=500, method="DELETE")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state != JupyterState.LOGGED_OUT
        if self.delete_immediate:
            self.state[user] = JupyterState.LOGGED_IN
        else:
            now = current_datetime(microseconds=True)
            self._delete_at[user] = now + timedelta(seconds=5)
        return CallbackResult(status=202)

    def create_session(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/user/{user}/api/sessions")
        assert user not in self.sessions
        if JupyterAction.CREATE_SESSION in self._fail.get(user, {}):
            return CallbackResult(status=500, method="POST")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LAB_RUNNING
        assert kwargs["json"]["kernel"]["name"] == "LSST"
        assert kwargs["json"]["name"] == "(no notebook)"
        assert kwargs["json"]["type"] == "console"
        session = JupyterLabSession(
            session_id=uuid4().hex,
            kernel_id=uuid4().hex,
            websocket=AsyncMock(),
        )
        self.sessions[user] = session
        return CallbackResult(
            status=201,
            payload={
                "id": session.session_id,
                "kernel": {"id": session.kernel_id},
            },
        )

    def delete_session(self, url: URL, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        session_id = self.sessions[user].session_id
        assert str(url).endswith(f"/user/{user}/api/sessions/{session_id}")
        if JupyterAction.DELETE_SESSION in self._fail.get(user, {}):
            return CallbackResult(status=500, method="DELETE")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LAB_RUNNING
        del self.sessions[user]
        return CallbackResult(status=204)

    @staticmethod
    def _get_user(authorization: str) -> str:
        """Get the user from the Authorization header."""
        assert authorization.startswith("Bearer ")
        token = authorization.split(" ", 1)[1]
        user = urlsafe_b64decode(token[3:].split(".", 1)[0].encode())
        return user.decode()


class MockJupyterWebSocket(Mock):
    """Simulate the WebSocket connection to a Jupyter Lab.

    Note
    ----
    The methods are named the reverse of what you would expect.  For example,
    ``send_json`` receives a message, and ``receive_json`` returns a message.
    This is so that this class can be used as a mock of an
    `~aiohttp.ClientWebSocketResponse`.
    """

    def __init__(self, user: str, session_id: str) -> None:
        super().__init__(spec=ClientWebSocketResponse)
        self.user = user
        self.session_id = session_id
        self._header: Optional[dict[str, str]] = None
        self._code: Optional[str] = None
        self._state: dict[str, Any] = {}

    async def send_json(self, message: dict[str, Any]) -> None:
        assert message == {
            "header": {
                "username": self.user,
                "version": "5.0",
                "session": self.session_id,
                "msg_id": ANY,
                "msg_type": "execute_request",
            },
            "parent_header": {},
            "channel": "shell",
            "content": {
                "code": ANY,
                "silent": False,
                "store_history": False,
                "user_expressions": {},
                "allow_stdin": False,
            },
            "metadata": {},
            "buffers": {},
        }
        self._header = message["header"]
        self._code = message["content"]["code"]

    async def receive_json(self) -> dict[str, Any]:
        assert self._header
        if self._code == _GET_NODE:
            self._code = None
            return {
                "msg_type": "stream",
                "parent_header": self._header,
                "content": {"text": "some-node"},
            }
        elif self._code == "long_error_for_test()":
            self._code = None
            error = ""
            line = "this is a single line of output to test trimming errors"
            for i in range(int(3000 / len(line))):
                error += f"{line} #{i}\n"
            return {
                "msg_type": "error",
                "parent_header": self._header,
                "content": {"traceback": error},
            }
        elif self._code:
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exec(self._code, self._state)
                self._code = None
                return {
                    "msg_type": "stream",
                    "parent_header": self._header,
                    "content": {"text": output.getvalue()},
                }
            except Exception:
                result = {
                    "msg_type": "error",
                    "parent_header": self._header,
                    "content": {"traceback": format_exc()},
                }
                self._header = None
                return result
        else:
            result = {
                "msg_type": "execute_reply",
                "parent_header": self._header,
                "content": {"status": "ok"},
            }
            self._header = None
            return result


def mock_jupyter(mocked: aioresponses) -> MockJupyter:
    """Set up a mock JupyterHub/Lab that always returns success.

    Currently only handles a lab spawn and then shutdown.  Behavior will
    eventually be configurable.
    """
    mock = MockJupyter()
    mocked.get(_url("hub/login"), callback=mock.login, repeat=True)
    mocked.get(_url("hub/spawn"), repeat=True)
    mocked.post(_url("hub/spawn"), callback=mock.spawn, repeat=True)
    mocked.get(
        _url("hub/spawn-pending/[^/]+$", regex=True),
        callback=mock.spawn_pending,
        repeat=True,
    )
    mocked.get(
        _url("hub/user/[^/]+/lab$", regex=True),
        callback=mock.missing_lab,
        repeat=True,
    )
    mocked.get(
        _url("hub/api/users/[^/]+$", regex=True),
        callback=mock.user,
        repeat=True,
    )
    mocked.get(
        _url("hub/api/users/[^/]+/server/progress$", regex=True),
        callback=mock.progress,
        repeat=True,
    )
    mocked.delete(
        _url("hub/api/users/[^/]+/server", regex=True),
        callback=mock.delete_lab,
        repeat=True,
    )
    mocked.get(
        _url(r"user/[^/]+/lab", regex=True), callback=mock.lab, repeat=True
    )
    mocked.post(
        _url("user/[^/]+/api/sessions", regex=True),
        callback=mock.create_session,
        repeat=True,
    )
    mocked.delete(
        _url("user/[^/]+/api/sessions/[^/]+$", regex=True),
        callback=mock.delete_session,
        repeat=True,
    )
    return mock


def mock_jupyter_websocket(
    url: str, jupyter: MockJupyter
) -> MockJupyterWebSocket:
    """Create a new mock ClientWebSocketResponse that simulates a lab."""
    match = re.search("/user/([^/]+)/api/kernels/([^/]+)/channels", url)
    assert match
    user = match.group(1)
    assert user
    session = jupyter.sessions[user]
    assert match.group(2) == session.kernel_id
    return MockJupyterWebSocket(user, session.session_id)
