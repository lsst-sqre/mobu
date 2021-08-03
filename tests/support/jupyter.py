"""A mock JupyterHub/Lab for tests."""

from __future__ import annotations

import re
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

from aioresponses import CallbackResult

from mobu.config import config
from mobu.jupyterclient import JupyterLabSession

if TYPE_CHECKING:
    from re import Pattern
    from typing import Any, Dict, Optional, Union

    from aioresponses import aioresponses


class JupyterAction(Enum):
    LOGIN = "login"
    HOME = "home"
    HUB = "hub"
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


def _url(route: str, regex: bool = False) -> Union[str, Pattern[str]]:
    """Construct a URL for JupyterHub/Proxy."""
    if not regex:
        return f"{config.environment_url}/nb/{route}"

    prefix = re.escape(f"{config.environment_url}/nb/")
    return re.compile(prefix + route)


class MockJupyter:
    """A mock Jupyter state machine.

    This should be invoked via mocked HTTP calls so that tests can simulate
    making REST calls to the real JupyterHub/Lab.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, JupyterLabSession] = {}
        self.state: Dict[str, JupyterState] = {}
        self.delete_immediate = True
        self._delete_at: Dict[str, Optional[datetime]] = {}
        self._fail: Dict[str, Dict[JupyterAction, bool]] = {}

    def fail(self, user: str, action: JupyterAction) -> None:
        """Configure the given action to fail for the given user."""
        if user not in self._fail:
            self._fail[user] = {}
        self._fail[user][action] = True

    def login(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.LOGIN in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LOGGED_OUT:
            self.state[user] = JupyterState.LOGGED_IN
        return CallbackResult(status=200)

    def home(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.HOME in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LAB_RUNNING:
            delete_at = self._delete_at.get(user)
            if delete_at and datetime.now(tz=timezone.utc) > delete_at:
                del self._delete_at[user]
                self.state[user] = JupyterState.LOGGED_IN
        if state in (JupyterState.SPAWN_PENDING, JupyterState.LAB_RUNNING):
            return CallbackResult(
                status=200, body="<p>My Server</p>", content_type="text/html"
            )
        else:
            return CallbackResult(
                status=200,
                body="<p>Start My Server</p>",
                content_type="text/html",
            )

    def hub(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        if JupyterAction.HUB in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        if state == JupyterState.LOGGED_OUT:
            redirect_to = _url("hub/login")
        elif state == JupyterState.LOGGED_IN:
            redirect_to = _url("hub/spawn")
        elif state == JupyterState.SPAWN_PENDING:
            redirect_to = _url(f"hub/spawn-pending/{user}")
        elif state == JupyterState.LAB_RUNNING:
            redirect_to = _url(f"user/{user}/lab")
        return CallbackResult(status=307, headers={"Location": redirect_to})

    def spawn(self, url: str, **kwargs: Any) -> CallbackResult:
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

    def spawn_pending(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/spawn-pending/{user}")
        if JupyterAction.SPAWN_PENDING in self._fail.get(user, {}):
            return CallbackResult(status=500)
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state == JupyterState.SPAWN_PENDING
        self.state[user] = JupyterState.LAB_RUNNING
        return CallbackResult(status=200)

    def missing_lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/user/{user}/lab")
        return CallbackResult(status=503)

    def lab(self, url: str, **kwargs: Any) -> CallbackResult:
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

    def delete_lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/users/{user}/server")
        if JupyterAction.DELETE_LAB in self._fail.get(user, {}):
            return CallbackResult(status=500, method="DELETE")
        state = self.state.get(user, JupyterState.LOGGED_OUT)
        assert state != JupyterState.LOGGED_OUT
        if self.delete_immediate:
            self.state[user] = JupyterState.LOGGED_IN
        else:
            now = datetime.now(tz=timezone.utc)
            self._delete_at[user] = now + timedelta(seconds=5)
        return CallbackResult(status=202)

    def create_session(self, url: str, **kwargs: Any) -> CallbackResult:
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

    def delete_session(self, url: str, **kwargs: Any) -> CallbackResult:
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


def mock_jupyter(mocked: aioresponses) -> MockJupyter:
    """Set up a mock JupyterHub/Lab that always returns success.

    Currently only handles a lab spawn and then shutdown.  Behavior will
    eventually be configurable.
    """
    mock = MockJupyter()
    mocked.get(_url("hub/login"), callback=mock.login, repeat=True)
    mocked.get(_url("hub"), callback=mock.hub, repeat=True)
    mocked.get(_url("hub/home"), callback=mock.home, repeat=True)
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
