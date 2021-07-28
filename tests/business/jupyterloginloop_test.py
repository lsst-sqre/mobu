"""Test the login monkey."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest

from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.jupyter import JupyterState

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient

    from tests.support.jupyter import MockJupyter


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, jupyter: MockJupyter, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {"settle_time": 0, "login_idle_time": 0},
            "business": "JupyterLoginLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop.  Make sure nothing fails.
    finished = False
    while not finished:
        await asyncio.sleep(0.5)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["failure_count"] == 0
        if data["business"]["success_count"] > 0:
            finished = True

    r = await client.get("/mobu/flocks/test/monkeys/testuser1")
    assert r.status_code == 200
    assert r.json() == {
        "name": "testuser1",
        "business": {
            "failure_count": 0,
            "name": "JupyterLoginLoop",
            "success_count": 1,
            "timings": ANY,
        },
        "restart": False,
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "username": "testuser1",
        },
    }

    # Check that the lab is shut down properly between iterations.
    assert jupyter.state["testuser1"] == JupyterState.LOGGED_IN

    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Starting up" in r.text
    assert "Exception thrown" not in r.text

    r = await client.delete("/mobu/flocks/test")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_reuse_lab(
    client: AsyncClient, jupyter: MockJupyter, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {
                "settle_time": 0,
                "login_idle_time": 0,
                "delete_lab": False,
            },
            "business": "JupyterLoginLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop.  Make sure nothing fails.
    finished = False
    while not finished:
        await asyncio.sleep(0.5)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        if r.json()["business"]["success_count"] > 0:
            finished = True

    # Check that the lab is still running between iterations.
    assert jupyter.state["testuser1"] == JupyterState.LAB_RUNNING
