"""A mock JupyterHub for tests."""

from __future__ import annotations

from base64 import urlsafe_b64decode
from enum import Enum
from typing import TYPE_CHECKING

from aioresponses import CallbackResult

from mobu.config import Configuration

if TYPE_CHECKING:
    from typing import Any, Dict

    from aioresponses import aioresponses


class JupyterHubState(Enum):
    LOGGED_OUT = "logged out"
    LOGGED_IN = "logged in"
    SPAWN_PENDING = "spawn pending"
    LAB_RUNNING = "lab running"


def _url(route: str) -> str:
    """Construct a URL for JupyterHub."""
    return f"{Configuration.environment_url}/nb/{route}"


class MockJupyterHub:
    """A mock JupyterHub state machine.

    This should be invoked via mocked HTTP calls so that tests can simulate
    making REST calls to the real JupyterHub.
    """

    def __init__(self) -> None:
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
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.SPAWN_PENDING
        self.state[user] = JupyterHubState.LAB_RUNNING
        return CallbackResult(
            status=307, headers={"Location": _url(f"user/{user}/lab?")}
        )

    def lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LAB_RUNNING
        return CallbackResult(status=200)

    def delete_lab(self, url: str, **kwargs: Any) -> CallbackResult:
        user = self._get_user(kwargs["headers"]["Authorization"])
        state = self.state.get(user, JupyterHubState.LOGGED_OUT)
        assert state == JupyterHubState.LAB_RUNNING
        self.state[user] = JupyterHubState.LOGGED_OUT
        return CallbackResult(status=202)

    @staticmethod
    def _get_user(authorization: str) -> str:
        """Get the user from the Authorization header."""
        assert authorization.startswith("Bearer ")
        token = authorization.split(" ", 1)[1]
        user = urlsafe_b64decode(token[3:].split(".", 1)[0].encode())
        return user.decode()


def mock_jupyterhub(mocked: aioresponses, user: str) -> None:
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
        _url(f"hub/spawn-pending/{user}"),
        callback=mock.finish_spawn,
        repeat=True,
    )
    mocked.get(_url(f"user/{user}/lab?"), callback=mock.lab, repeat=True)
    mocked.delete(
        _url(f"hub/api/users/{user}/server"),
        callback=mock.delete_lab,
        repeat=True,
    )
