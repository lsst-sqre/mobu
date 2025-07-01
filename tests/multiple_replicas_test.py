"""Tests for autostarting flocks of monkeys."""

from __future__ import annotations

from unittest.mock import ANY

import pytest
from httpx import AsyncClient


async def assert_users(client: AsyncClient, users: list[int]) -> None:
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
        for i in users
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


@pytest.mark.asyncio
@pytest.mark.usefixtures("_multi_replica_0")
async def test_replica_0(client: AsyncClient) -> None:
    await assert_users(client=client, users=[1, 4, 7, 10])


@pytest.mark.asyncio
@pytest.mark.usefixtures("_multi_replica_1")
async def test_replica_1(client: AsyncClient) -> None:
    await assert_users(client=client, users=[2, 5, 8])


@pytest.mark.asyncio
@pytest.mark.usefixtures("_multi_replica_2")
async def test_replica_2(client: AsyncClient) -> None:
    await assert_users(client=client, users=[3, 6, 9])
