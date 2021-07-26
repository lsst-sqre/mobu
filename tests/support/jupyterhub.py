"""A mock JupyterHub for tests."""

from __future__ import annotations

import re
from base64 import urlsafe_b64decode
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from aioresponses import CallbackResult

from mobu.config import config
from mobu.jupyterclient import JupyterLabSession

if TYPE_CHECKING:
    from re import Pattern
    from typing import Any, Dict, Union

    from aioresponses import aioresponses


class JupyterHubState(Enum):
    LOGGED_OUT = "logged out"
    LOGGED_IN = "logged in"
    SPAWN_PENDING = "spawn pending"
    LAB_RUNNING = "lab running"


def _url(route: str, regex: bool = False) -> Union[str, Pattern[str]]:
    """Construct a URL for JupyterHub."""
    if not regex:
        return f"{config.environment_url}/nb/{route}"

    prefix = re.escape(f"{config.environment_url}/nb/")
    return re.compile(prefix + route)


class MockJupyterHub:
    """A mock JupyterHub state machine.

    This should be invoked via mocked HTTP calls so that tests can simulate
    making REST calls to the real JupyterHub.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, Any] = {}
        self.state: Dict[str, JupyterHubState] = {}

    def login(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        self.state[user] = JupyterHubState.LOGGED_IN
        return CallbackResult(status=200)

    def hub(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        if state == JupyterHubState.LOGGED_OUT:
            redirect_to = _url("hub/login")
        elif state == JupyterHubState.LOGGED_IN:
            redirect_to = _url("hub/spawn")
        elif state == JupyterHubState.SPAWN_PENDING:
            redirect_to = _url(f"hub/spawn-pending/{user}")
        elif state == JupyterHubState.LAB_RUNNING:
            redirect_to = _url(f"hub/spawn-pending/{user}")
        return CallbackResult(status=307, headers={"Location": redirect_to})

    def spawn(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LOGGED_IN
        self.state[user] = JupyterHubState.SPAWN_PENDING
        return CallbackResult(
            status=302,
            headers={"Location": f"/nb/hub/spawn-pending/{user}"},
        )

    def finish_spawn(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/hub/spawn-pending/{user}")
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.SPAWN_PENDING
        self.state[user] = JupyterHubState.LAB_RUNNING
        return CallbackResult(
            status=307, headers={"Location": _url(f"user/{user}/lab")}
        )

    def lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/user/{user}/lab")
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LAB_RUNNING
        return CallbackResult(status=200)

    def delete_lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/users/{user}/server")
        self.state[user] = JupyterHubState.LOGGED_OUT
        return CallbackResult(status=202)

    def create_session(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        assert str(url).endswith(f"/user/{user}/api/sessions")
        assert user not in self.sessions
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LAB_RUNNING
        assert kwargs["json"]["kernel"]["name"] == "LSST"
        assert kwargs["json"]["name"] == "(no notebook)"
        assert kwargs["json"]["type"] == "console"
        session = JupyterLabSession(
            session_id=uuid4().hex, kernel_id=uuid4().hex, websocket=None
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
        session = self.sessions[user]
        assert str(url).endswith(
            f"/user/{user}/api/sessions/{session.session_id}"
        )
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LAB_RUNNING
        del self.sessions[user]
        return CallbackResult(status=204)

    @staticmethod
    def _get_user(authorization: str) -> str:
        """Get the user from the Authorization header."""
        assert authorization.startswith("Bearer ")
        token = authorization.split(" ", 1)[1]
        user = urlsafe_b64decode(token[3:].split(".", 1)[0].encode())
        return user.decode()


def mock_jupyterhub(mocked: aioresponses) -> None:
    """Set up a mock JupyterHub that always returns success.

    Currently only handles a lab spawn and then shutdown.  Behavior will
    eventually be configurable.
    """
    mock = MockJupyterHub()
    mocked.get(_url("hub/login"), callback=mock.login, repeat=True)
    mocked.get(_url("hub"), callback=mock.hub, repeat=True)
    mocked.get(_url("hub/spawn"), repeat=True)
    mocked.post(_url("hub/spawn"), callback=mock.spawn, repeat=True)
    mocked.get(
        _url("hub/spawn-pending/[^/]+$", regex=True),
        callback=mock.finish_spawn,
        repeat=True,
    )
    mocked.get(
        _url("user/[^/]+/lab?", regex=True), callback=mock.lab, repeat=True
    )
    mocked.delete(
        _url("hub/api/users/[^/]+/server", regex=True),
        callback=mock.delete_lab,
        repeat=True,
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
