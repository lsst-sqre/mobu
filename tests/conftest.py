"""Test fixtures for mobu tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from textwrap import dedent
from unittest.mock import DEFAULT, patch

import pytest
import pytest_asyncio
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import HttpUrl
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook

from mobu import main
from mobu.config import GitHubCiApp, GitHubRefreshApp, config
from mobu.services.business.gitlfs import GitLFSBusiness

from .support.constants import (
    TEST_BASE_URL,
    TEST_GITHUB_CI_APP_PRIVATE_KEY,
    TEST_GITHUB_CI_APP_SECRET,
    TEST_GITHUB_REFRESH_APP_SECRET,
)
from .support.gafaelfawr import make_gafaelfawr_token
from .support.github import GitHubMocker
from .support.gitlfs import (
    no_git_lfs_data,
    uninstall_git_lfs,
    verify_uuid_contents,
)
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


@pytest.fixture
def _enable_github_ci_app(tmp_path: Path) -> Iterator[None]:
    """Enable the GitHub CI app functionality.
    """
    github_config = tmp_path / "github_config.yaml"
    github_config.write_text(
        dedent("""
        users:
        - username: bot-mobu-unittest-1
        - username: bot-mobu-unittest-2
        accepted_github_orgs:
          - org1
          - org2
          - lsst-sqre
    """)
    )
    config.github_ci_app.id = 1
    config.github_ci_app.enabled = True
    config.github_ci_app.webhook_secret = TEST_GITHUB_CI_APP_SECRET
    config.github_ci_app.private_key = TEST_GITHUB_CI_APP_PRIVATE_KEY
    config.github_config_path = github_config

    yield

    config.github_ci_app = GitHubCiApp()
    config.github_config_path = None


@pytest.fixture
def _enable_github_refresh_app(tmp_path: Path) -> Iterator[None]:
    """Enable the GitHub Refresh app routes.

    We need to reload the main module here because including the router is done
    conditionally on module import.
    """
    github_config = tmp_path / "github_config.yaml"
    github_config.write_text(
        dedent("""
        users:
        - username: bot-mobu-unittest-1
        - username: bot-mobu-unittest-2
        accepted_github_orgs:
          - org1
          - org2
          - lsst-sqre
    """)
    )

    config.github_refresh_app.enabled = True
    config.github_refresh_app.webhook_secret = TEST_GITHUB_REFRESH_APP_SECRET
    config.github_config_path = github_config
    reload(main)

    yield

    config.github_refresh_app = GitHubRefreshApp()
    config.github_config_path = None
    reload(main)


@pytest_asyncio.fixture
async def app(jupyter: MockJupyter) -> AsyncIterator[FastAPI]:
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
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url=TEST_BASE_URL,
        headers={"X-Auth-Request-User": "someuser"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an anonymous ``httpx.AsyncClient`` configured to talk to the test
    app.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url=TEST_BASE_URL,
    ) as client:
        yield client


@pytest.fixture
def jupyter(respx_mock: respx.Router) -> Iterator[MockJupyter]:
    """Mock out JupyterHub and Jupyter labs."""
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

    with patch("mobu.storage.nublado.websocket_connect") as mock:
        mock.side_effect = mock_connect
        yield jupyter_mock


@pytest.fixture
def slack(respx_mock: respx.Router) -> Iterator[MockSlackWebhook]:
    config.alert_hook = HttpUrl("https://slack.example.com/XXXX")
    yield mock_slack_webhook(str(config.alert_hook), respx_mock)
    config.alert_hook = None


@pytest.fixture
def gitlfs_mock() -> Iterator[None]:
    with patch.object(
        GitLFSBusiness,
        "_install_git_lfs",
        side_effect=uninstall_git_lfs,
        autospec=True,
    ):
        with patch.object(
            GitLFSBusiness,
            "_check_uuid_pointer",
            side_effect=verify_uuid_contents,
            autospec=True,
        ):
            with patch.object(
                GitLFSBusiness,
                "_add_git_lfs_data",
                side_effect=no_git_lfs_data,
                autospec=True,
            ):
                yield None


@pytest.fixture
def _no_monkey_business() -> Iterator[None]:
    """Prevent any flock monkeys from actually doing any business."""
    with patch.multiple(
        "mobu.services.flock.Monkey", start=DEFAULT, stop=DEFAULT
    ):
        yield


@pytest.fixture
def github_mocker() -> Iterator[GitHubMocker]:
    github_mocker = GitHubMocker()
    with github_mocker.router:
        yield github_mocker
