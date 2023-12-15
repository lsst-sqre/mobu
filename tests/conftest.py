"""Test fixtures for mobu tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import HttpUrl
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook

from mobu import main
from mobu.config import config

from .support.cachemachine import MockCachemachine, mock_cachemachine
from .support.constants import TEST_BASE_URL
from .support.gafaelfawr import make_gafaelfawr_token
from .support.jupyter import (
    MockJupyter,
    MockJupyterWebSocket,
    mock_jupyter,
    mock_jupyter_websocket,
)


@pytest.fixture(autouse=True)
def _configure() -> Iterator[None]:
    """Set minimal configuration settings.

    Add an environment URL for testing purposes and create a Gafaelfawr admin
    token and add it to the configuration.

    This is an autouse fixture, so it will ensure that each test gets the
    minimal test configuration and a unique admin token that is replaced after
    the test runs.
    """
    config.environment_url = HttpUrl("https://test.example.com")
    config.gafaelfawr_token = make_gafaelfawr_token()
    yield
    config.environment_url = None
    config.gafaelfawr_token = None


@pytest_asyncio.fixture
async def app(
    jupyter: MockJupyter, cachemachine: MockCachemachine
) -> AsyncIterator[FastAPI]:
    """Return a configured test application.

    Wraps the application in a lifespan manager so that startup and shutdown
    events are sent during test execution.

    Notes
    -----
    This must depend on the Jupyter mock since otherwise the JupyterClient
    mocking is undone before the app is shut down, which causes it to try to
    make real web socket calls.

    A tests in :file:`business/jupyterloginloop_test.py` depends on the exact
    shutdown timeout.
    """
    async with LifespanManager(main.app, shutdown_timeout=10):
        yield main.app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` configured to talk to the test app."""
    url = TEST_BASE_URL
    headers = {"X-Auth-Request-User": "someuser"}
    async with AsyncClient(app=app, base_url=url, headers=headers) as client:
        yield client


@pytest.fixture
def cachemachine(respx_mock: respx.Router) -> MockCachemachine:
    """Mock out cachemachine."""
    return mock_cachemachine(respx_mock)


@pytest.fixture
def jupyter(respx_mock: respx.Router) -> Iterator[MockJupyter]:
    """Mock out JupyterHub/Lab."""
    jupyter_mock = mock_jupyter(respx_mock)

    # respx has no mechanism to mock aconnect_ws, so we have to do it
    # ourselves.
    @asynccontextmanager
    async def mock_connect(
        url: str,
        extra_headers: dict[str, str],
        max_size: int | None,
        open_timeout: int,
    ) -> AsyncIterator[MockJupyterWebSocket]:
        yield mock_jupyter_websocket(url, extra_headers, jupyter_mock)

    with patch("mobu.storage.jupyter.websocket_connect") as mock:
        mock.side_effect = mock_connect
        yield jupyter_mock


@pytest.fixture
def slack(respx_mock: respx.Router) -> Iterator[MockSlackWebhook]:
    config.alert_hook = HttpUrl("https://slack.example.com/XXXX")
    yield mock_slack_webhook(str(config.alert_hook), respx_mock)
    config.alert_hook = None
