"""Test fixtures for mobu tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import DEFAULT, patch

import pytest
import pytest_asyncio
import respx
import safir.logging
import structlog
import websockets
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from rubin.nublado.client.models import User
from rubin.nublado.client.testing import (
    MockJupyter,
    MockJupyterWebSocket,
    mock_jupyter,
    mock_jupyter_websocket,
)
from safir.testing.sentry import (
    Captured,
    capture_events_fixture,
    sentry_init_fixture,
)
from safir.testing.slack import MockSlackWebhook, mock_slack_webhook
from structlog.stdlib import BoundLogger

from mobu import main
from mobu.dependencies.config import config_dependency
from mobu.dependencies.context import context_dependency
from mobu.events import Events
from mobu.exceptions import SubprocessError
from mobu.sentry import before_send, send_all_error_transactions
from mobu.services.business.gitlfs import GitLFSBusiness
from mobu.services.business.nublado import _GET_IMAGE, _GET_NODE

from .support.config import config_path
from .support.constants import (
    TEST_BASE_URL,
    TEST_GITHUB_CI_APP_PRIVATE_KEY,
    TEST_GITHUB_CI_APP_SECRET,
    TEST_GITHUB_REFRESH_APP_SECRET,
)
from .support.gafaelfawr import make_gafaelfawr_token, mock_gafaelfawr
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
def _configure(environment_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimal configuration settings.

    Add an environment URL for testing purposes and create a Gafaelfawr admin
    token and add it to the configuration.

    This is an autouse fixture, so it will ensure that each test gets the
    minimal test configuration and a unique admin token that is replaced after
    the test runs.
    """
    monkeypatch.setenv("MOBU_GAFAELFAWR_TOKEN", make_gafaelfawr_token())
    config_dependency.set_path(config_path("base"))


@pytest.fixture
def test_filesystem() -> Iterator[Path]:
    with TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def _enable_github_ci_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Enable the GitHub CI app functionality."""
    monkeypatch.setenv("MOBU_GITHUB_CI_APP_ID", "1")
    monkeypatch.setenv(
        "MOBU_GITHUB_CI_APP_WEBHOOK_SECRET", TEST_GITHUB_CI_APP_SECRET
    )
    monkeypatch.setenv(
        "MOBU_GITHUB_CI_APP_PRIVATE_KEY", TEST_GITHUB_CI_APP_PRIVATE_KEY
    )
    config_dependency.set_path(config_path("github_ci_app"))

    yield

    config_dependency.set_path(config_path("base"))


@pytest.fixture
def _disable_file_logging() -> None:
    """Disable monkey file logging."""
    config_dependency.set_path(config_path("base_no_file_logging"))


@pytest.fixture
def _multi_replica_0(respx_mock: respx.Router) -> None:
    """Set config for multi-instance."""
    mock_gafaelfawr(respx_mock, any_uid=True)
    config_dependency.set_path(config_path("multi_replica_0"))


@pytest.fixture
def _multi_replica_1(respx_mock: respx.Router) -> None:
    """Set config for multi-instance."""
    mock_gafaelfawr(respx_mock, any_uid=True)
    config_dependency.set_path(config_path("multi_replica_1"))


@pytest.fixture
def _multi_replica_2(respx_mock: respx.Router) -> None:
    """Set config for multi-instance."""
    mock_gafaelfawr(respx_mock, any_uid=True)
    config_dependency.set_path(config_path("multi_replica_2"))


@pytest.fixture
def _enable_github_refresh_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Enable the GitHub refresh app functionality."""
    monkeypatch.setenv("MOBU_GITHUB_REFRESH_APP_ID", "1")
    monkeypatch.setenv(
        "MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET",
        TEST_GITHUB_REFRESH_APP_SECRET,
    )
    config_dependency.set_path(config_path("github_refresh_app"))
    yield

    config_dependency.set_path(config_path("base"))


@pytest_asyncio.fixture
async def app() -> AsyncGenerator[FastAPI]:
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
def events(app: FastAPI) -> Events:
    """Event publishers from a configured test application."""
    return context_dependency.process_context.events


@pytest_asyncio.fixture
async def client(app: FastAPI, test_user: User) -> AsyncGenerator[AsyncClient]:
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
async def anon_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Return an anonymous ``httpx.AsyncClient`` configured to talk to the test
    app.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=TEST_BASE_URL,
    ) as client:
        yield client


@pytest.fixture(ids=["shared", "subdomain"], params=[False, True])
def jupyter(
    respx_mock: respx.Router,
    environment_url: str,
    test_filesystem: Path,
    request: pytest.FixtureRequest,
) -> Iterator[MockJupyter]:
    """Mock out JupyterHub and Jupyter labs."""
    jupyter_mock = mock_jupyter(
        respx_mock,
        base_url=environment_url,
        user_dir=test_filesystem,
        use_subdomains=request.param,
    )

    # respx has no mechanism to mock aconnect_ws, so we have to do it
    # ourselves.
    @asynccontextmanager
    async def mock_connect(
        url: str,
        additional_headers: dict[str, str],
        max_size: int | None,
        open_timeout: int,
    ) -> AsyncGenerator[MockJupyterWebSocket]:
        yield mock_jupyter_websocket(url, additional_headers, jupyter_mock)

    with patch.object(websockets, "connect") as mock:
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
def slack(
    respx_mock: respx.Router, monkeypatch: pytest.MonkeyPatch
) -> MockSlackWebhook:
    alert_hook = "https://slack.example.com/XXXX"
    monkeypatch.setenv("MOBU_ALERT_HOOK", alert_hook)
    config_dependency.set_path(config_path("base"))
    return mock_slack_webhook(alert_hook, respx_mock)


@pytest.fixture
def gitlfs_fail_mock() -> Iterator[None]:
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
                side_effect=SubprocessError("No git-lfs"),
                autospec=True,
            ):
                yield None


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


@pytest.fixture
def sentry_items(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Captured]:
    """Mock Sentry transport and yield a list that will contain all events."""
    with sentry_init_fixture() as init:
        init(
            traces_sample_rate=1.0,
            before_send=before_send,
            before_send_transaction=send_all_error_transactions,
        )
        events = capture_events_fixture(monkeypatch)
        yield events()
