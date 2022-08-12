"""Test the JupyterPythonLoop business logic."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY

import pytest
from aioresponses import aioresponses
from httpx import AsyncClient

from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.slack import MockSlack
from tests.support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(
        mock_aioresponses, username="testuser1", uid=1000, gid=1000
    )

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "max_executions": 3,
            },
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.  Make sure nothing fails.
    data = await wait_for_business(client, "testuser1")
    assert data == {
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
            "gidnumber": 1000,
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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "options": {
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "max_executions": 3,
            },
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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "options": {
                "code": 'raise Exception("some error")',
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "max_executions": 1,
            },
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["failure_count"] == 1

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
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nRecommended (Weekly 2021_33)",
                            "verbatim": True,
                        },
                        {"type": "mrkdwn", "text": "*Node*\nsome-node"},
                    ],
                },
            ],
            "attachments": [
                {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ANY,
                                "verbatim": True,
                            },
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
                    ]
                }
            ],
        }
    ]
    error = slack.alerts[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert "Exception: some error" in error


@pytest.mark.asyncio
async def test_long_error(
    client: AsyncClient, slack: MockSlack, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "options": {
                "code": "long_error_for_test()",
                "jupyter": {
                    "image_class": "by-reference",
                    "image_reference": (
                        "registry.hub.docker.com/lsstsqre/sciplat-lab"
                        ":d_2021_08_30"
                    ),
                },
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "max_executions": 1,
            },
            "business": "JupyterPythonLoop",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["failure_count"] == 1

    # Check that an appropriate error was posted.
    error = ""
    line = "this is a single line of output to test trimming errors"
    for i in range(5, 54):
        error += f"{line} #{i}\n"
    assert 2977 - len(line) <= len(error) <= 2977
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
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nd_2021_08_30",
                            "verbatim": True,
                        },
                        {"type": "mrkdwn", "text": "*Node*\nsome-node"},
                    ],
                },
            ],
            "attachments": [
                {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Error*\n```\n{error}```",
                                "verbatim": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*Code executed*\n"
                                    "```\nlong_error_for_test()\n```"
                                ),
                                "verbatim": True,
                            },
                        },
                    ]
                }
            ],
        }
    ]
