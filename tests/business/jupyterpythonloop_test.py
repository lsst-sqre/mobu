"""Test the JupyterPythonLoop business logic."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest

from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, jupyter: None, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {"idle_time": 2, "settle_time": 2, "max_executions": 2},
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    r = await client.get("/mobu/flocks/test/monkeys/testuser1")
    assert r.status_code == 200
    assert r.json() == {
        "name": "testuser1",
        "business": {
            "failure_count": 0,
            "name": "JupyterPythonLoop",
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
    }

    # Wait until we've finished at least one loop.  Make sure nothing fails.
    finished = False
    while not finished:
        await asyncio.sleep(1)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["failure_count"] == 0
        if data["business"]["success_count"] > 0:
            finished = True

    # Get the client log and check no exceptions were thrown.
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Exception thrown" not in r.text

    r = await client.delete("/mobu/flocks/test")
    assert r.status_code == 204
