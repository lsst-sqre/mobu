"""Tests for Monkeyflocker."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import httpx
import pytest
from click.testing import CliRunner
from safir.testing.uvicorn import UvicornProcess, spawn_uvicorn

from mobu.config import config
from monkeyflocker.cli import main

from .support.gafaelfawr import make_gafaelfawr_token

FLOCK_CONFIG = """
name: basic
count: 1
user_spec:
  username_prefix: testuser
scopes: ["exec:notebook"]
business: Business
"""


@pytest.fixture
def monkeyflocker_app(tmp_path: Path) -> Iterator[UvicornProcess]:
    """Run the application as a separate process for monkeyflocker access."""
    assert config.environment_url
    config.gafaelfawr_token = make_gafaelfawr_token()
    uvicorn = spawn_uvicorn(
        working_directory=tmp_path,
        factory="tests.support.monkeyflocker:create_app",
        env={
            "ENVIRONMENT_URL": str(config.environment_url),
            "GAFAELFAWR_TOKEN": config.gafaelfawr_token,
        },
    )
    yield uvicorn
    config.gafaelfawr_token = None
    uvicorn.process.terminate()


def test_start_report_stop(
    tmp_path: Path, monkeyflocker_app: UvicornProcess
) -> None:
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
            monkeyflocker_app.url,
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
    r = httpx.get(f"{monkeyflocker_app.url}/mobu/flocks/basic")
    assert r.status_code == 200
    assert r.json() == expected

    result = runner.invoke(
        main,
        [
            "report",
            "-e",
            monkeyflocker_app.url,
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
            monkeyflocker_app.url,
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

    r = httpx.get(f"{monkeyflocker_app.url}/mobu/flocks/basic")
    assert r.status_code == 404
