"""Test fixtures for mobu tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aioresponses import aioresponses
from asgi_lifespan import LifespanManager
from httpx import AsyncClient

from mobu import main
from mobu.config import config
from tests.support.gafaelfawr import make_gafaelfawr_token

if TYPE_CHECKING:
    from typing import AsyncIterator, Iterator

    from fastapi import FastAPI


@pytest.fixture(autouse=True)
def admin_token() -> Iterator[str]:
    """Create a Gafaelfawr admin token and add it to the configuration.

    This is an autouse fixture, so it will ensure that each test gets a unique
    admin token that is replaced after the test runs.
    """
    admin_token = make_gafaelfawr_token()
    config.gafaelfawr_token = admin_token
    yield admin_token
    config.gafaelfawr_token = "None"


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
def mock_aioresponses() -> Iterator[aioresponses]:
    with aioresponses() as mocked:
        yield mocked
