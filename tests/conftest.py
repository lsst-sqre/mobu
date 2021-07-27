"""Test fixtures for mobu tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from aioresponses import aioresponses
from asgi_lifespan import LifespanManager
from httpx import AsyncClient

from mobu import main
from mobu.config import config
from mobu.jupyterclient import JupyterClient
from tests.support.gafaelfawr import make_gafaelfawr_token
from tests.support.jupyterhub import mock_jupyterhub

if TYPE_CHECKING:
    from typing import AsyncIterator, Iterator

    from fastapi import FastAPI


@pytest.fixture(autouse=True)
def configure() -> Iterator[None]:
    """Set minimal configuration settings.

    Add an environment URL for testing purposes and create a Gafaelfawr admin
    token and add it to the configuration.

    This is an autouse fixture, so it will ensure that each test gets the
    minimal test configuration and a unique admin token that is replaced after
    the test runs.
    """
    config.environment_url = "https://test.example.com/"
    config.gafaelfawr_token = make_gafaelfawr_token()
    yield
    config.environment_url = ""
    config.gafaelfawr_token = None


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    """Return a configured test application.

    Wraps the application in a lifespan manager so that startup and shutdown
    events are sent during test execution.
    """
    async with LifespanManager(main.app):
        yield main.app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` configured to talk to the test app."""
    async with AsyncClient(app=app, base_url="https://example.com/") as client:
        yield client


@pytest.fixture
def jupyterhub(mock_aioresponses: aioresponses) -> Iterator[None]:
    """Mock out JupyterHub."""
    mock_jupyterhub(mock_aioresponses)

    # aioresponses has no mechanism to mock ws_connect, so we can't properly
    # test JupyterClient.run_python.  For now, just mock it out entirely.
    with patch.object(JupyterClient, "run_python") as mock:
        mock.return_value = "4"
        yield


@pytest.fixture
def mock_aioresponses() -> Iterator[aioresponses]:
    """Set up aioresponses for aiohttp mocking."""
    with aioresponses() as mocked:
        yield mocked
