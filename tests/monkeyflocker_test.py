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

from mobu.dependencies.config import config_dependency
from monkeyflocker.cli import main

from .support.config import config_path

FLOCK_CONFIG = """
name: basic
count: 1
user_spec:
  username_prefix: bot-mobu-testuser
scopes: ["exec:notebook"]
business:
  type: EmptyLoop
"""


@pytest.fixture
def monkeyflocker_app(tmp_path: Path) -> Iterator[UvicornProcess]:
    """Run the application as a separate process for monkeyflocker access."""
    config = config_dependency.config
    assert config.gafaelfawr_token
    assert config.environment_url
    uvicorn = spawn_uvicorn(
        working_directory=tmp_path,
        factory="tests.support.monkeyflocker:create_app",
        env={
            "MOBU_GAFAELFAWR_TOKEN": config.gafaelfawr_token,
            "MOBU_CONFIG_PATH": str(config_path("base")),
        },
    )
    yield uvicorn
    uvicorn.process.terminate()


def test_start_report_refresh_stop(
    tmp_path: Path, monkeyflocker_app: UvicornProcess
) -> None:
    config = config_dependency.config
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
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    expected: dict[str, Any] = {
        "name": "basic",
        "config": {
            "name": "basic",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {"type": "EmptyLoop"},
        },
        "monkeys": [
            {
                "name": "bot-mobu-testuser1",
                "business": {
                    "failure_count": 0,
                    "name": "EmptyLoop",
                    "refreshing": ANY,
                    "success_count": ANY,
                },
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "bot-mobu-testuser1",
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
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    with (output_path / "bot-mobu-testuser1_stats.json").open("r") as f:
        assert expected["monkeys"][0] == json.load(f)
    log = (output_path / "bot-mobu-testuser1_log.txt").read_text()
    assert "Idling..." in log

    shutil.rmtree(str(output_path))

    result = runner.invoke(
        main,
        [
            "refresh",
            "-e",
            monkeyflocker_app.url,
            "-o",
            str(output_path),
            "-k",
            config.gafaelfawr_token,
            "basic",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

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
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    with (output_path / "bot-mobu-testuser1_stats.json").open("r") as f:
        assert expected["monkeys"][0] == json.load(f)
    log = (output_path / "bot-mobu-testuser1_log.txt").read_text()
    assert "Idling..." in log

    r = httpx.get(f"{monkeyflocker_app.url}/mobu/flocks/basic")
    assert r.status_code == 404
