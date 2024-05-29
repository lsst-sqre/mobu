"""Tests for autostarting flocks of monkeys."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient

from mobu.config import config

from .support.gafaelfawr import mock_gafaelfawr
from .support.jupyter import MockJupyter
from .support.util import wait_for_flock_start

AUTOSTART_CONFIG = """
- name: basic
  count: 10
  user_spec:
    username_prefix: testuser
    uid_start: 1000
    gid_start: 2000
  scopes: ["exec:notebook"]
  business:
    type: EmptyLoop
- name: python
  count: 2
  users:
    - username: python
      uidnumber: 60000
    - username: otherpython
      uidnumber: 70000
  scopes: ["exec:notebook"]
  restart: true
  business:
    type: NubladoPythonLoop
    restart: True
    options:
      image:
        image_class: latest-weekly
        size: Large
      spawn_settle_time: 0
"""


@pytest.fixture(autouse=True)
def _configure_autostart(
    tmp_path: Path, respx_mock: respx.Router
) -> Iterator[None]:
    """Set up the autostart configuration."""
    mock_gafaelfawr(respx_mock, any_uid=True)
    config.autostart = tmp_path / "autostart.yaml"
    config.autostart.write_text(AUTOSTART_CONFIG)
    yield
    config.autostart = None


@pytest.mark.asyncio
async def test_autostart(client: AsyncClient, jupyter: MockJupyter) -> None:
    r = await client.get("/mobu/flocks/basic")
    assert r.status_code == 200
    expected_monkeys = [
        {
            "name": f"testuser{i:02d}",
            "business": {
                "failure_count": 0,
                "name": "EmptyLoop",
                "refreshing": False,
                "success_count": ANY,
                "timings": ANY,
            },
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
            "business": {"type": "EmptyLoop"},
        },
        "monkeys": expected_monkeys,
    }

    await wait_for_flock_start(client, "python")
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
            "business": {
                "type": "NubladoPythonLoop",
                "restart": True,
                "options": {
                    "image": {
                        "image_class": "latest-weekly",
                        "size": "Large",
                    },
                    "spawn_settle_time": 0,
                },
            },
        },
        "monkeys": [
            {
                "name": "python",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "description": "Recommended (Weekly 2077_43)",
                        "reference": (
                            "lighthouse.ceres/library/sketchbook:recommended"
                        ),
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                    "timings": ANY,
                },
                "state": "RUNNING",
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
                        "description": "Recommended (Weekly 2077_43)",
                        "reference": (
                            "lighthouse.ceres/library/sketchbook:recommended"
                        ),
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                    "timings": ANY,
                },
                "state": "RUNNING",
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
