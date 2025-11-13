"""Tests for autostarting flocks of monkeys."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient

from mobu.dependencies.config import config_dependency

from .support.config import config_path
from .support.gafaelfawr import mock_gafaelfawr
from .support.util import wait_for_flock_start

# Use the Jupyter mock for all tests in this file.
pytestmark = pytest.mark.usefixtures("mock_jupyter")


@pytest.fixture(autouse=True)
def _configure_autostart(respx_mock: respx.Router) -> Iterator[None]:
    """Set up the autostart configuration."""
    config_dependency.set_path(config_path("autostart"))
    mock_gafaelfawr(respx_mock, any_uid=True)
    yield
    config_dependency.set_path(config_path("base"))


@pytest.mark.asyncio
async def test_autostart(client: AsyncClient) -> None:
    r = await client.get("/mobu/flocks/basic")
    assert r.status_code == 200
    expected_monkeys = [
        {
            "name": f"bot-mobu-testuser{i:02d}",
            "business": {
                "failure_count": 0,
                "name": "EmptyLoop",
                "refreshing": False,
                "success_count": ANY,
            },
            "state": ANY,
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "uidnumber": 1000 + i - 1,
                "gidnumber": 2000 + i - 1,
                "username": f"bot-mobu-testuser{i:02d}",
                "groups": [],
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
                "username_prefix": "bot-mobu-testuser",
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
                    "username": "bot-mobu-python",
                    "uidnumber": 60000,
                },
                {
                    "username": "bot-mobu-otherpython",
                    "uidnumber": 70000,
                },
            ],
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "restart": True,
                "options": {
                    "image": {
                        "class": "latest-weekly",
                        "size": "Large",
                    },
                    "spawn_settle_time": 0,
                },
            },
        },
        "monkeys": [
            {
                "name": "bot-mobu-python",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "description": ANY,
                        "reference": ANY,
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                },
                "state": "RUNNING",
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "bot-mobu-python",
                    "uidnumber": 60000,
                    "gidnumber": 60000,
                    "groups": [],
                },
            },
            {
                "name": "bot-mobu-otherpython",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "description": ANY,
                        "reference": ANY,
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                },
                "state": "RUNNING",
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "bot-mobu-otherpython",
                    "uidnumber": 70000,
                    "gidnumber": 70000,
                    "groups": [],
                },
            },
        ],
    }

    r = await client.delete("/mobu/flocks/python")
    assert r.status_code == 204
    r = await client.delete("/mobu/flocks/basic")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_batched_autostart(client: AsyncClient) -> None:
    r = await client.get("/mobu/flocks/basic")
    assert r.status_code == 200
    expected_monkeys = [
        {
            "name": f"bot-mobu-testuser{i:02d}",
            "business": {
                "failure_count": 0,
                "name": "EmptyLoop",
                "refreshing": False,
                "success_count": ANY,
            },
            "state": ANY,
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "uidnumber": 1000 + i - 1,
                "gidnumber": 2000 + i - 1,
                "groups": [],
                "username": f"bot-mobu-testuser{i:02d}",
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
                "username_prefix": "bot-mobu-testuser",
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
                    "username": "bot-mobu-python",
                    "uidnumber": 60000,
                },
                {
                    "username": "bot-mobu-otherpython",
                    "uidnumber": 70000,
                },
            ],
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "restart": True,
                "options": {
                    "image": {
                        "class": "latest-weekly",
                        "size": "Large",
                    },
                    "spawn_settle_time": 0,
                },
            },
        },
        "monkeys": [
            {
                "name": "bot-mobu-python",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "description": ANY,
                        "reference": ANY,
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                },
                "state": "RUNNING",
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "bot-mobu-python",
                    "uidnumber": 60000,
                    "gidnumber": 60000,
                    "groups": [],
                },
            },
            {
                "name": "bot-mobu-otherpython",
                "business": {
                    "failure_count": 0,
                    "image": {
                        "description": ANY,
                        "reference": ANY,
                    },
                    "name": "NubladoPythonLoop",
                    "refreshing": False,
                    "success_count": ANY,
                },
                "state": "RUNNING",
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "username": "bot-mobu-otherpython",
                    "uidnumber": 70000,
                    "gidnumber": 70000,
                    "groups": [],
                },
            },
        ],
    }

    r = await client.delete("/mobu/flocks/python")
    assert r.status_code == 204
    r = await client.delete("/mobu/flocks/basic")
    assert r.status_code == 204
