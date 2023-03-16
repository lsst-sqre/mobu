"""Tests for Monkeyflocker."""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import httpx
import pytest
from click.testing import CliRunner

from mobu.config import config
from monkeyflocker.cli import main

APP_SOURCE = """
from collections.abc import Awaitable, Callable

from aioresponses import aioresponses
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from mobu.config import config
from mobu.main import app
from tests.support.gafaelfawr import make_gafaelfawr_token, mock_gafaelfawr
from tests.support.jupyter import mock_jupyter


# Pretend Gafaelfawr is doing authentication in front of mobu.  This is a
# total hack based on https://github.com/tiangolo/fastapi/issues/2727 that
# adds the header that would have been added by Gafaelfawr.  Unfortunately,
# there's no documented way to modify request headers in middleware, so we
# have to muck about with internals.
class AddAuthHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.headers.__dict__["_list"].append(
            (b"x-auth-request-user", b"someuser")
        )
        return await call_next(request)


# Add the new middleware.
app.add_middleware(AddAuthHeaderMiddleware)


@app.on_event("startup")
async def startup_event() -> None:
    config.gafaelfawr_token = make_gafaelfawr_token()
    mocked = aioresponses()
    mocked.start()
    mock_gafaelfawr(mocked)
    mock_jupyter(mocked)
"""

FLOCK_CONFIG = """
name: basic
count: 1
user_spec:
  username_prefix: testuser
scopes: ["exec:notebook"]
business: Business
"""


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    """Wait until a server accepts connections on the specified port."""
    deadline = time.time() + timeout
    while True:
        socket_timeout = deadline - time.time()
        if socket_timeout < 0.0:
            assert False, f"Server did not start on port {port} in {timeout}s"
        try:
            s = socket.socket()
            s.settimeout(socket_timeout)
            s.connect(("localhost", port))
        except socket.timeout:
            pass
        except socket.error as e:
            if e.errno not in [errno.ETIMEDOUT, errno.ECONNREFUSED]:
                raise
        else:
            s.close()
            return
        time.sleep(0.1)


@pytest.fixture
def app_url(tmp_path: Path) -> Iterator[str]:
    """Run the application as a separate process for monkeyflocker access."""
    app_path = tmp_path / "testing.py"
    app_path.write_text(APP_SOURCE)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]

    cmd = ["uvicorn", "--fd", "0", "testing:app"]
    logging.info("Starting server with command %s", " ".join(cmd))
    p = subprocess.Popen(
        cmd,
        cwd=str(tmp_path),
        stdin=s.fileno(),
        env={
            **os.environ,
            "ENVIRONMENT_URL": config.environment_url,
            "PYTHONPATH": os.getcwd(),
        },
    )
    s.close()

    logging.info("Waiting for server to start")
    _wait_for_server(port)

    try:
        yield f"http://localhost:{port}"
    finally:
        p.terminate()


def test_start_report_stop(tmp_path: Path, app_url: str) -> None:
    runner = CliRunner()
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(FLOCK_CONFIG)
    output_path = tmp_path / "output"
    assert config.gafaelfawr_token

    result = runner.invoke(
        main,
        [
            "start",
            "-e",
            app_url,
            "-f",
            str(spec_path),
            "-k",
            config.gafaelfawr_token,
        ],
    )
    print(result.stdout)
    assert result.exit_code == 0

    expected: dict[str, Any] = {
        "name": "basic",
        "config": {
            "name": "basic",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": "Business",
        },
        "monkeys": [
            {
                "name": "testuser1",
                "business": {
                    "failure_count": 0,
                    "name": "Business",
                    "success_count": ANY,
                    "timings": ANY,
                },
                "restart": False,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "testuser1",
                },
            },
        ],
    }
    r = httpx.get(f"{app_url}/mobu/flocks/basic")
    assert r.status_code == 200
    assert r.json() == expected

    result = runner.invoke(
        main,
        [
            "report",
            "-e",
            app_url,
            "-o",
            str(output_path),
            "-k",
            config.gafaelfawr_token,
            "basic",
        ],
    )
    assert result.exit_code == 0

    with (output_path / "testuser1_stats.json").open("r") as f:
        assert expected["monkeys"][0] == json.load(f)
    log = (output_path / "testuser1_log.txt").read_text()
    assert "Idling..." in log

    shutil.rmtree(str(output_path))
    result = runner.invoke(
        main,
        [
            "stop",
            "-e",
            app_url,
            "-o",
            str(output_path),
            "-k",
            config.gafaelfawr_token,
            "basic",
        ],
    )
    assert result.exit_code == 0

    with (output_path / "testuser1_stats.json").open("r") as f:
        assert expected["monkeys"][0] == json.load(f)
    log = (output_path / "testuser1_log.txt").read_text()
    assert "Idling..." in log

    r = httpx.get(f"{app_url}/mobu/flocks/basic")
    assert r.status_code == 404
