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

    from tests.support.slack import MockSlack


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {"settle_time": 0, "max_executions": 3},
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop.  Make sure nothing fails.
    for _ in range(1, 10):
        await asyncio.sleep(1)
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
            "name": "JupyterPythonLoop",
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

    # Get the client log and check no exceptions were thrown.
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Exception thrown" not in r.text

    r = await client.delete("/mobu/flocks/test")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_server_shutdown(
    client: AsyncClient, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 20,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {"settle_time": 0, "max_executions": 3},
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait for a second so that all the monkeys get started.
    await asyncio.sleep(1)

    # Now end the test without shutting anything down explicitly.  This tests
    # that server shutdown correctly stops everything and cleans up resources.


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient, slack: MockSlack, mock_aioresponses: aioresponses
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
                "code": 'raise Exception("some error")',
                "settle_time": 0,
                "max_executions": 1,
            },
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop.
    for _ in range(1, 10):
        await asyncio.sleep(1)
        r = await client.get("/mobu/flocks/test/monkeys/testuser1")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["success_count"] == 0
        if data["business"]["failure_count"] > 1:
            break

    # Check that an appropriate error was posted.
    assert slack.alerts == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running code",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": "*User*\ntestuser1"},
                        {"type": "mrkdwn", "text": "*Event*\nexecute_code"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Code executed*\n"
                            '```\nraise Exception("some error")\n```'
                        ),
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ANY, "verbatim": True},
                },
                {"type": "divider"},
            ],
        }
    ]
    error = slack.alerts[0]["blocks"][3]["text"]["text"]
    assert "some error" in error
