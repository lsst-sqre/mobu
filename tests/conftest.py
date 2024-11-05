"""Test fixtures for mobu tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from unittest.mock import DEFAULT, patch

import pytest
import pytest_asyncio
import respx
import safir.logging
import structlog
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import HttpUrl
from rubin.nublado.client import NubladoClient
from rubin.nublado.client.models import User
from rubin.nublado.client.testing import (
    MockJupyter,
    MockJupyterWebSocket,
    mock_jupyter,
    mock_jupyter_websocket,
)
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook
from structlog.stdlib import BoundLogger

from mobu import main
from mobu.config import config
from mobu.services.business.gitlfs import GitLFSBusiness
from mobu.services.business.nublado import _GET_IMAGE, _GET_NODE

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


@pytest.fixture(autouse=True)
def environment_url() -> str:
    return TEST_BASE_URL


@pytest.fixture
def test_user() -> User:
    uname = "someuser"
    return User(username=uname, token=make_gafaelfawr_token(uname))


@pytest.fixture
def configured_logger() -> BoundLogger:
    safir.logging.configure_logging(
        name="nublado-client",
        profile=safir.logging.Profile.development,
        log_level=safir.logging.LogLevel.DEBUG,
    )
    return structlog.get_logger("nublado-client")


@pytest.fixture(autouse=True)
def _configure(environment_url: str) -> Iterator[None]:
    """Set minimal configuration settings.

    Add an environment URL for testing purposes and create a Gafaelfawr admin
    token and add it to the configuration.

    This is an autouse fixture, so it will ensure that each test gets the
    minimal test configuration and a unique admin token that is replaced after
    the test runs.
    """
    config.environment_url = HttpUrl(environment_url)
    config.gafaelfawr_token = make_gafaelfawr_token()
    config.available_services = {"some_service", "some_other_service"}
    yield
    config.environment_url = None
    config.gafaelfawr_token = None
    config.available_services = set()


@pytest.fixture
def test_filesystem() -> Iterator[Path]:
    with TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def _enable_github_ci_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Enable the GitHub CI app functionality."""
    github_config = tmp_path / "github_ci_app_config.yaml"
    github_config.write_text(
        dedent("""
          users:
            - username: bot-mobu-unittest-1
            - username: bot-mobu-unittest-2
          accepted_github_orgs:
            - org1
            - org2
            - lsst-sqre
          scopes:
            - "exec:notebook"
            - "exec:portal"
            - "read:image"
            - "read:tap"
    """)
    )
    monkeypatch.setenv("MOBU_GITHUB_CI_APP_ID", "1")
    monkeypatch.setenv(
        "MOBU_GITHUB_CI_APP_WEBHOOK_SECRET", TEST_GITHUB_CI_APP_SECRET
    )
    monkeypatch.setenv(
        "MOBU_GITHUB_CI_APP_PRIVATE_KEY", TEST_GITHUB_CI_APP_PRIVATE_KEY
    )
    monkeypatch.setattr(config, "github_ci_app_config_path", github_config)


@pytest.fixture
def _enable_github_refresh_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Enable the GitHub refresh app functionality."""
    github_config = tmp_path / "github_ci_app_refresh.yaml"
    github_config.write_text(
        dedent("""
          accepted_github_orgs:
            - org1
            - org2
            - lsst-sqre
    """)
    )
    monkeypatch.setenv("MOBU_GITHUB_REFRESH_APP_ID", "1")
    monkeypatch.setenv(
        "MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET",
        TEST_GITHUB_REFRESH_APP_SECRET,
    )
    monkeypatch.setattr(
        config, "github_refresh_app_config_path", github_config
    )


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
    app = main.create_app()
    async with LifespanManager(app, shutdown_timeout=10):
        yield app


@pytest.fixture
def configured_nublado_client(
    app: FastAPI,
    environment_url: str,
    configured_logger: BoundLogger,
    test_user: User,
    test_filesystem: Path,
    jupyter: MockJupyter,
) -> NubladoClient:
    n_client = NubladoClient(
        user=test_user, logger=configured_logger, base_url=environment_url
    )
    # For the test client, we also have to add the two headers that would
    # be added by a GafaelfawrIngress in real life.
    n_client._client.headers["X-Auth-Request-User"] = test_user.username
    n_client._client.headers["X-Auth-Request-Token"] = test_user.token
    return n_client


@pytest_asyncio.fixture
async def client(
    app: FastAPI,
    test_user: User,
    jupyter: MockJupyter,
) -> AsyncIterator[AsyncClient]:
    """Return an ``httpx.AsyncClient`` configured to talk to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=TEST_BASE_URL,
        headers={
            "X-Auth-Request-User": test_user.username,
            "X-Auth-Request-Token": test_user.token,
        },
    ) as client:
        yield client


@pytest_asyncio.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an anonymous ``httpx.AsyncClient`` configured to talk to the test
    app.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=TEST_BASE_URL,
    ) as client:
        yield client


@pytest.fixture
def jupyter(
    respx_mock: respx.Router,
    environment_url: str,
    test_filesystem: Path,
) -> Iterator[MockJupyter]:
    """Mock out JupyterHub and Jupyter labs."""
    jupyter_mock = mock_jupyter(
        respx_mock, base_url=environment_url, user_dir=test_filesystem
    )

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

    with patch("rubin.nublado.client.nubladoclient.websocket_connect") as mock:
        mock.side_effect = mock_connect
        # Register some code we call over and over and over...
        jupyter_mock.register_python_result(_GET_NODE, "Node1")
        jupyter_mock.register_python_result(
            _GET_IMAGE,
            (
                "lighthouse.ceres/library/sketchbook:recommended\n"
                "Recommended (Weekly 2077_43)\n"
            ),
        )
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
