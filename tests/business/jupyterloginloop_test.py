"""Test the login monkey."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import ANY
from urllib.parse import urljoin

import pytest

from mobu.config import config
from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.jupyter import JupyterAction, JupyterState

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient

    from tests.support.jupyter import MockJupyter
    from tests.support.slack import MockSlack


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
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["failure_count"] == 0
        if data["business"]["success_count"] > 0:
            break

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
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        if r.json()["business"]["success_count"] > 0:
            break

    # Check that the lab is still running between iterations.
    assert jupyter.state["testuser1"] == JupyterState.LAB_RUNNING


@pytest.mark.asyncio
async def test_delayed_lab_delete(
    client: AsyncClient, jupyter: MockJupyter, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 5,
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

    # End the test without shutting anything down.  The test asgi-lifespan
    # wrapper has a shutdown timeout of ten seconds and delete will take
    # five seconds, so the test is that everything shuts down cleanly without
    # throwing exceptions.
    jupyter.delete_immediate = False


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlack,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.fail("testuser2", JupyterAction.SPAWN)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
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

    # Wait until we've finished at least one loop.
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get("/mobu/flocks/test/monkeys/testuser2")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["success_count"] == 0
        if data["business"]["failure_count"] > 0:
            break

    # Check that an appropriate error was posted.
    url = urljoin(config.environment_url, "/nb/hub/spawn")
    assert slack.alerts == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Status 500 from POST {url}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": "*User*\ntestuser2"},
                        {"type": "mrkdwn", "text": "*Event*\nensure_lab"},
                        {"type": "mrkdwn", "text": "*Message*\nfoo"},
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]
