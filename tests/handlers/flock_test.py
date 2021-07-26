"""Test the handlers for flocks and their monkeys."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest

from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from typing import Any, Dict

    from aioresponses import aioresponses
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_start_stop(
    client: AsyncClient, jupyter: None, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    config = {
        "name": "test",
        "count": 1,
        "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
        "scopes": ["exec:notebook"],
        "business": "Business",
    }
    r = await client.put("/mobu/flocks", json=config)
    assert r.status_code == 201
    expected: Dict[str, Any] = {
        "name": "test",
        "config": {
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "business": "Business",
        },
        "monkeys": [
            {
                "name": "testuser1",
                "business": {
                    "failure_count": 0,
                    "name": "Business",
                    "success_count": 0,
                    "timings": ANY,
                },
                "restart": False,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "uidnumber": 1000,
                    "username": "testuser1",
                },
            },
        ],
    }
    assert r.json() == expected
    assert r.headers["Location"] == "/mobu/flocks/test"

    r = await client.get("/mobu/flocks")
    assert r.status_code == 200
    assert r.json() == ["test"]

    r = await client.get("/mobu/flocks/test")
    assert r.status_code == 200
    assert r.json() == expected

    r = await client.get("/mobu/flocks/test/monkeys")
    assert r.status_code == 200
    assert r.json() == ["testuser1"]

    r = await client.get("/mobu/flocks/test/monkeys/testuser1")
    assert r.status_code == 200
    assert r.json() == expected["monkeys"][0]

    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "text/plain" in r.headers["Content-Type"]
    assert "filename" in r.headers["Content-Disposition"]
    assert "test-testuser1-" in r.headers["Content-Disposition"]
    assert "Idling..." in r.text

    r = await client.get("/mobu/flocks/other")
    assert r.status_code == 404
    r = await client.delete("/mobu/flocks/other")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/other/monkeys")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/test/monkeys/testuser2")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/test/monkeys/testuser2/log")
    assert r.status_code == 404

    r = await client.delete("/mobu/flocks/test")
    assert r.status_code == 204

    r = await client.get("/mobu/flocks/test")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/test/monkeys")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/test/monkeys/testuser1")
    assert r.status_code == 404
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 404

    r = await client.get("/mobu/flocks")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_user_list(
    client: AsyncClient, jupyter: None, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    config = {
        "name": "test",
        "count": 2,
        "users": [
            {
                "username": "testuser",
                "uidnumber": 1000,
            },
            {
                "username": "otheruser",
                "uidnumber": 60000,
            },
        ],
        "scopes": ["exec:notebook"],
        "business": "Business",
    }
    r = await client.put("/mobu/flocks", json=config)
    assert r.status_code == 201
    expected: Dict[str, Any] = {
        "name": "test",
        "config": config,
        "monkeys": [
            {
                "name": "testuser",
                "business": {
                    "failure_count": 0,
                    "name": "Business",
                    "success_count": 0,
                    "timings": ANY,
                },
                "restart": False,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "uidnumber": 1000,
                    "username": "testuser",
                },
            },
            {
                "name": "otheruser",
                "business": {
                    "failure_count": 0,
                    "name": "Business",
                    "success_count": 0,
                    "timings": ANY,
                },
                "restart": False,
                "state": ANY,
                "user": {
                    "scopes": ["exec:notebook"],
                    "token": ANY,
                    "uidnumber": 60000,
                    "username": "otheruser",
                },
            },
        ],
    }
    assert r.json() == expected
    assert r.headers["Location"] == "/mobu/flocks/test"

    r = await client.get("/mobu/flocks/test/monkeys/testuser")
    assert r.status_code == 200
    assert r.json() == expected["monkeys"][0]

    r = await client.get("/mobu/flocks/test/monkeys/otheruser")
    assert r.status_code == 200
    assert r.json() == expected["monkeys"][1]

    # Intentionally do not delete the flock to check whether aiojobs will
    # shut down properly when the server is shut down.


@pytest.mark.asyncio
async def test_errors(
    client: AsyncClient, jupyter: None, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    # Both users and user_spec given.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "users": [
                {
                    "username": "testuser",
                    "uidnumber": 1000,
                },
                {
                    "username": "otheruser",
                    "uidnumber": 60000,
                },
            ],
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": [],
            "business": "Business",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {
                "loc": ["body", "user_spec"],
                "msg": "both users and user_spec provided",
                "type": "value_error",
            }
        ]
    }

    # Neither users nor user_spec given.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "scopes": [],
            "business": "Business",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {
                "loc": ["body", "user_spec"],
                "msg": "one of users or user_spec must be provided",
                "type": "value_error",
            }
        ]
    }

    # Too many users for the size of the flock.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "users": [
                {
                    "username": "testuser",
                    "uidnumber": 1000,
                },
                {
                    "username": "otheruser",
                    "uidnumber": 60000,
                },
                {
                    "username": "thirduser",
                    "uidnumber": 70000,
                },
            ],
            "scopes": [],
            "business": "Business",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {
                "loc": ["body", "users"],
                "msg": "users list must contain 2 elements",
                "type": "value_error",
            },
            {
                "loc": ["body", "user_spec"],
                "msg": "one of users or user_spec must be provided",
                "type": "value_error",
            },
        ]
    }

    # Not enough users for the size of the flock.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "users": [
                {
                    "username": "testuser",
                    "uidnumber": 1000,
                }
            ],
            "scopes": [],
            "business": "Business",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {
                "loc": ["body", "users"],
                "msg": "users list must contain 2 elements",
                "type": "value_error",
            },
            {
                "loc": ["body", "user_spec"],
                "msg": "one of users or user_spec must be provided",
                "type": "value_error",
            },
        ]
    }

    # Unknown business.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "business": "UnknownBusiness",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": [
            {
                "ctx": {"given": "UnknownBusiness", "permitted": ANY},
                "loc": ["body", "business"],
                "msg": ANY,
                "type": "value_error.const",
            }
        ]
    }
