"""Tests for autostarting flocks of monkeys."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest

from mobu.config import config
from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Iterator

    from aioresponses import aioresponses
    from httpx import AsyncClient


AUTOSTART_CONFIG = """
- name: basic
  count: 10
  user_spec:
    username_prefix: testuser
    uid_start: 1000
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
    jupyter_options_form:
      image: "registry.hub.docker.com/lsstsqre/sciplat-lab:recommended"
      image_dropdown: use_image_from_dropdown
      size: Small
    settle_time: 45
  scopes: ["exec:notebook"]
  restart: true
  business: JupyterPythonLoop
"""


@pytest.fixture(autouse=True)
def configure_autostart(
    tmp_path: Path, mock_aioresponses: aioresponses
) -> Iterator[None]:
    """Set up the autostart configuration."""
    mock_gafaelfawr(mock_aioresponses)
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
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
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
                "jupyter_options_form": {
                    "image": (
                        "registry.hub.docker.com/lsstsqre/sciplat-lab"
                        ":recommended"
                    ),
                    "image_dropdown": "use_image_from_dropdown",
                    "size": "Small",
                },
                "settle_time": 45,
            },
        },
        "monkeys": [
            {
                "name": "python",
                "business": {
                    "failure_count": 0,
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
                },
            },
            {
                "name": "otherpython",
                "business": {
                    "failure_count": 0,
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
                },
            },
        ],
    }

    r = await client.delete("/mobu/flocks/python")
    assert r.status_code == 204
    r = await client.delete("/mobu/flocks/basic")
    assert r.status_code == 204
