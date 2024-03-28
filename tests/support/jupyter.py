"""A mock JupyterHub and lab for tests."""

from __future__ import annotations

import asyncio
import json
import os
import re
from base64 import urlsafe_b64decode
from collections.abc import AsyncIterator
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from io import StringIO
from re import Pattern
from traceback import format_exc
from typing import Any
from unittest.mock import ANY
from urllib.parse import parse_qs
from uuid import uuid4

import respx
from httpx import Request, Response
from safir.datetime import current_datetime

from mobu.config import config
from mobu.services.business.nublado import _GET_IMAGE, _GET_NODE


class JupyterAction(Enum):
    """Possible actions on the Jupyter lab state machine."""

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


@dataclass
class JupyterLabSession:
    """Metadata for an open Jupyter lab session."""

    session_id: str
    kernel_id: str


class JupyterState(Enum):
    """Possible states the Jupyter lab can be in."""

    LOGGED_OUT = "logged out"
    LOGGED_IN = "logged in"
    SPAWN_PENDING = "spawn pending"
    LAB_RUNNING = "lab running"


def _url(route: str) -> str:
    """Construct a URL for JupyterHub or its proxy."""
    assert config.environment_url
    base_url = str(config.environment_url).rstrip("/")
    return f"{base_url}/nb/{route}"


def _url_regex(route: str) -> Pattern[str]:
    """Construct a regex matching a URL for JupyterHub or its proxy."""
    assert config.environment_url
    base_url = str(config.environment_url).rstrip("/")
    return re.compile(re.escape(f"{base_url}/nb/") + route)


class MockJupyter:
    """A mock Jupyter state machine.

    This should be invoked via mocked HTTP calls so that tests can simulate
    making REST calls to the real JupyterHub and lab. It simulates the process
    of spawning a lab, creating a session, and running code within that
    session.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, JupyterLabSession] = {}
        self.state: dict[str, JupyterState] = {}
        self.delete_immediate = True
        self.spawn_timeout = False
        self.redirect_loop = False
        self.lab_form: dict[str, dict[str, str]] = {}
        self._delete_at: dict[str, datetime | None] = {}
        self._fail: dict[str, dict[JupyterAction, bool]] = {}
        self._hub_xsrf = os.urandom(8).hex()
        self._lab_xsrf = os.urandom(8).hex()

    @staticmethod
    def get_user(authorization: str) -> str:
        """Get the user from the Authorization header."""
        assert authorization.startswith("Bearer ")
        token = authorization.split(" ", 1)[1]
        user = urlsafe_b64decode(token[3:].split(".", 1)[0].encode())
        return user.decode()

    def fail(self, user: str, action: JupyterAction) -> None:
        """Configure the given action to fail for the given user."""
        if user not in self._fail:
            self._fail[user] = {}
        self._fail[user][action] = True

    def login(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        if JupyterAction.LOGIN in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LOGGED_OUT:
            self.state[user] = JupyterState.LOGGED_IN
        xsrf = f"_xsrf={self._hub_xsrf}"
        return Response(200, request=request, headers={"Set-Cookie": xsrf})

    def user(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        if JupyterAction.USER in self._fail.get(user, {}):
            return Response(500, request=request)
        assert str(request.url).endswith(f"/hub/api/users/{user}")
        assert request.headers.get("x-xsrftoken") == self._hub_xsrf
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
        return Response(200, json=body, request=request)

    async def progress(self, request: Request) -> Response:
        if self.redirect_loop:
            return Response(
                303, headers={"Location": str(request.url)}, request=request
            )
        user = self.get_user(request.headers["Authorization"])
        expected_suffix = f"/hub/api/users/{user}/server/progress"
        assert str(request.url).endswith(expected_suffix)
        assert request.headers.get("x-xsrftoken") == self._hub_xsrf
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state in (JupyterState.SPAWN_PENDING, JupyterState.LAB_RUNNING)
        if JupyterAction.PROGRESS in self._fail.get(user, {}):
            body = (
                'data: {"progress": 0, "message": "Server requested"}\n\n'
                'data: {"progress": 50, "message": "Spawning server..."}\n\n'
                'data: {"progress": 75, "message": "Spawn failed!"}\n\n'
            )
        elif state == JupyterState.LAB_RUNNING:
            body = (
                'data: {"progress": 100, "ready": true, "message": "Ready"}\n'
                "\n"
            )
        elif self.spawn_timeout:
            # Cause the spawn to time out by pausing for longer than the test
            # should run for and then returning nothing.
            await asyncio.sleep(60)
            body = ""
        else:
            self.state[user] = JupyterState.LAB_RUNNING
            body = (
                'data: {"progress": 0, "message": "Server requested"}\n\n'
                'data: {"progress": 50, "message": "Spawning server..."}\n\n'
                'data: {"progress": 100, "ready": true, "message": "Ready"}\n'
                "\n"
            )
        return Response(
            200,
            text=body,
            headers={"Content-Type": "text/event-stream"},
            request=request,
        )

    def spawn(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        if JupyterAction.SPAWN in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LOGGED_IN
        assert request.headers.get("x-xsrftoken") == self._hub_xsrf
        self.state[user] = JupyterState.SPAWN_PENDING
        self.lab_form[user] = {
            k: v[0] for k, v in parse_qs(request.content.decode()).items()
        }
        url = _url(f"hub/spawn-pending/{user}")
        return Response(302, headers={"Location": url}, request=request)

    def spawn_pending(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/hub/spawn-pending/{user}")
        if JupyterAction.SPAWN_PENDING in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.SPAWN_PENDING
        assert request.headers.get("x-xsrftoken") == self._hub_xsrf
        return Response(200, request=request)

    def missing_lab(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/hub/user/{user}/lab")
        return Response(503, request=request)

    def lab(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/user/{user}/lab")
        if JupyterAction.LAB in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LAB_RUNNING:
            xsrf = f"_xsrf={self._lab_xsrf}"
            return Response(
                302,
                request=request,
                headers={
                    "Location": _url(f"user/{user}/callback"),
                    "Set-Cookie": xsrf,
                },
            )
        else:
            return Response(
                302,
                headers={"Location": _url(f"hub/user/{user}/lab")},
                request=request,
            )

    def lab_callback(self, request: Request) -> Response:
        """Simulate not setting the ``_xsrf`` cookie on first request.

        This implements a redirect from ``/user/username/lab`` to
        ``/user/username/callback``, followed by a 200, which is not how
        the lab does it (it has a much more complex redirect to the hub, back
        to a callback, and then back to the lab), but it's hopefully good
        enough to test handling of cookies during redirect chains for
        capturing the ``_xsrf`` cookie.
        """
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/user/{user}/callback")
        return Response(200, request=request)

    def delete_lab(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/users/{user}/server")
        assert request.headers.get("x-xsrftoken") == self._hub_xsrf
        if JupyterAction.DELETE_LAB in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state != JupyterState.LOGGED_OUT
        if self.delete_immediate:
            self.state[user] = JupyterState.LOGGED_IN
        else:
            now = current_datetime(microseconds=True)
            self._delete_at[user] = now + timedelta(seconds=5)
        return Response(202, request=request)

    def create_session(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        assert str(request.url).endswith(f"/user/{user}/api/sessions")
        assert request.headers.get("x-xsrftoken") == self._lab_xsrf
        assert user not in self.sessions
        if JupyterAction.CREATE_SESSION in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LAB_RUNNING
        body = json.loads(request.content.decode())
        assert body["kernel"]["name"] == "LSST"
        assert body["name"] == "(no notebook)"
        assert body["type"] == "console"
        session = JupyterLabSession(
            session_id=uuid4().hex, kernel_id=uuid4().hex
        )
        self.sessions[user] = session
        return Response(
            201,
            json={
                "id": session.session_id,
                "kernel": {"id": session.kernel_id},
            },
            request=request,
        )

    def delete_session(self, request: Request) -> Response:
        user = self.get_user(request.headers["Authorization"])
        session_id = self.sessions[user].session_id
        expected_suffix = f"/user/{user}/api/sessions/{session_id}"
        assert str(request.url).endswith(expected_suffix)
        assert request.headers.get("x-xsrftoken") == self._lab_xsrf
        if JupyterAction.DELETE_SESSION in self._fail.get(user, {}):
            return Response(500, request=request)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.LAB_RUNNING
        del self.sessions[user]
        return Response(204, request=request)


class MockJupyterWebSocket:
    """Simulate the WebSocket connection to a Jupyter Lab.

    Note
    ----
    The methods are named the reverse of what you would expect:  ``send``
    receives a message, and ``recv`` sends a message back to the caller. This
    is because this is a mock of a client library but is simulating a server,
    so is operating in the reverse direction.
    """

    def __init__(self, user: str, session_id: str) -> None:
        self.user = user
        self.session_id = session_id
        self._header: dict[str, str] | None = None
        self._code: str | None = None
        self._state: dict[str, Any] = {}

    async def close(self) -> None:
        pass

    async def send(self, message_str: str) -> None:
        message = json.loads(message_str)
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

    async def __aiter__(self) -> AsyncIterator[str]:
        while True:
            assert self._header
            response = self._build_response()
            yield json.dumps(response)

    def _build_response(self) -> dict[str, Any]:
        if self._code == _GET_IMAGE:
            self._code = None
            return {
                "msg_type": "stream",
                "parent_header": self._header,
                "content": {
                    "text": (
                        "lighthouse.ceres/library/sketchbook:recommended\n"
                        "Recommended (Weekly 2077_43)\n"
                    )
                },
            }
        elif self._code == _GET_NODE:
            self._code = None
            return {
                "msg_type": "stream",
                "parent_header": self._header,
                "content": {"text": "some-node"},
            }
        elif self._code == "long_error_for_test()":
            error = ""
            line = "this is a single line of output to test trimming errors"
            for i in range(int(3000 / len(line))):
                error += f"{line} #{i}\n"
            self._code = None
            return {
                "msg_type": "error",
                "parent_header": self._header,
                "content": {"traceback": error},
            }
        elif self._code:
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exec(self._code, self._state)  # noqa: S102
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


def mock_jupyter(respx_mock: respx.Router) -> MockJupyter:
    """Set up a mock JupyterHub and lab."""
    mock = MockJupyter()
    respx_mock.get(_url("hub/home")).mock(side_effect=mock.login)
    respx_mock.get(_url("hub/spawn")).mock(return_value=Response(200))
    respx_mock.post(_url("hub/spawn")).mock(side_effect=mock.spawn)
    regex = _url_regex("hub/spawn-pending/[^/]+$")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.spawn_pending)
    regex = _url_regex("hub/user/[^/]+/lab$")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.missing_lab)
    regex = _url_regex("hub/api/users/[^/]+$")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.user)
    regex = _url_regex("hub/api/users/[^/]+/server/progress$")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.progress)
    regex = _url_regex("hub/api/users/[^/]+/server")
    respx_mock.delete(url__regex=regex).mock(side_effect=mock.delete_lab)
    regex = _url_regex(r"user/[^/]+/lab")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.lab)
    regex = _url_regex(r"user/[^/]+/callback")
    respx_mock.get(url__regex=regex).mock(side_effect=mock.lab_callback)
    regex = _url_regex("user/[^/]+/api/sessions")
    respx_mock.post(url__regex=regex).mock(side_effect=mock.create_session)
    regex = _url_regex("user/[^/]+/api/sessions/[^/]+$")
    respx_mock.delete(url__regex=regex).mock(side_effect=mock.delete_session)
    return mock


def mock_jupyter_websocket(
    url: str, headers: dict[str, str], jupyter: MockJupyter
) -> MockJupyterWebSocket:
    """Create a new mock ClientWebSocketResponse that simulates a lab.

    Parameters
    ----------
    url
        URL of the request to open a WebSocket.
    headers
        Extra headers sent with that request.
    jupyter
        Mock JupyterHub.

    Returns
    -------
    MockJupyterWebSocket
        Mock WebSocket connection.
    """
    match = re.search("/user/([^/]+)/api/kernels/([^/]+)/channels", url)
    assert match
    user = match.group(1)
    assert user == jupyter.get_user(headers["authorization"])
    session = jupyter.sessions[user]
    assert match.group(2) == session.kernel_id
    return MockJupyterWebSocket(user, session.session_id)
