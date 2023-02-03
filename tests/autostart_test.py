"""Tests for autostarting flocks of monkeys."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from unittest.mock import ANY

import pytest
from aioresponses import aioresponses
from httpx import AsyncClient

from mobu.config import config
from tests.support.gafaelfawr import mock_gafaelfawr

AUTOSTART_CONFIG = """
- name: basic
  count: 10
  user_spec:
    username_prefix: testuser
    uid_start: 1000
    gid_start: 2000
  scopes: ["exec:notebook"]
  business: Business
- name: python
  count: 2
  users:
    - username: python
      uidnumber: 60000
    - username: otherpython
      uidnumber: 70000
  options:
    jupyter:
      image_class: latest-weekly
      image_size: Large
    spawn_settle_time: 10
  scopes: ["exec:notebook"]
  restart: true
  business: JupyterPythonLoop
"""


@pytest.fixture(autouse=True)
def configure_autostart(
    tmp_path: Path, mock_aioresponses: aioresponses
) -> Iterator[None]:
    """Set up the autostart configuration."""
    mock_gafaelfawr(mock_aioresponses, any_uid=True)
    autostart_path = tmp_path / "autostart.yaml"
    autostart_path.write_text(AUTOSTART_CONFIG)
    config.autostart = str(autostart_path)
    yield
    config.autostart = None


@pytest.mark.asyncio
async def test_autostart(client: AsyncClient) -> None:
    r = await client.get("/mobu/flocks/basic")
    assert r.status_code == 200
    expected_monkeys = [
        {
            "name": f"testuser{i:02d}",
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
                "uidnumber": 1000 + i - 1,
                "gidnumber": 2000 + i - 1,
                "username": f"testuser{i:02d}",
            },
        }
        for i in range(1, 11)
    ]
    assert r.json() == {
        "name": "basic",
        "config": {
            "name": "basic",
            "count": 10,
            "user_spec": {
                "username_prefix": "testuser",
                "uid_start": 1000,
                "gid_start": 2000,
            },
            "scopes": ["exec:notebook"],
            "business": "Business",
        },
        "monkeys": expected_monkeys,
    }

    r = await client.get("/mobu/flocks/python")
    assert r.status_code == 200
    assert r.json() == {
        "name": "python",
        "config": {
            "name": "python",
            "count": 2,
            "users": [
                {
                    "username": "python",
                    "uidnumber": 60000,
                },
                {
                    "username": "otherpython",
                    "uidnumber": 70000,
                },
            ],
            "scopes": ["exec:notebook"],
            "restart": True,
            "business": "JupyterPythonLoop",
            "options": {
                "jupyter": {
                    "image_class": "latest-weekly",
                    "image_size": "Large",
                },
                "spawn_settle_time": 10,
            },
        },
        "monkeys": [
            {
                "name": "python",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "digest": ANY,
                        "name": "Weekly 2023_05",
                        "path": (
                            "docker.io/lsstsqre/sciplat-lab" ":w_2023_05"
                        ),
                        "prepulled": True,
                        "tags": {"w_2023_05": "Weekly 2023_05"},
                    },
                    "name": "JupyterPythonLoop",
                    "success_count": ANY,
                    "timings": ANY,
                },
                "restart": True,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "python",
                    "uidnumber": 60000,
                    "gidnumber": 60000,
                },
            },
            {
                "name": "otherpython",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "digest": ANY,
                        "name": "Weekly 2023_05",
                        "path": (
                            "docker.io/lsstsqre/sciplat-lab" ":w_2023_05"
                        ),
                        "prepulled": True,
                        "tags": {"w_2023_05": "Weekly 2023_05"},
                    },
                    "name": "JupyterPythonLoop",
                    "success_count": ANY,
                    "timings": ANY,
                },
                "restart": True,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "otherpython",
                    "uidnumber": 70000,
                    "gidnumber": 70000,
                },
            },
        ],
    }

    r = await client.delete("/mobu/flocks/python")
    assert r.status_code == 204
    r = await client.delete("/mobu/flocks/basic")
    assert r.status_code == 204
