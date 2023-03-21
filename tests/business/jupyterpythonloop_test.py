"""Test the JupyterPythonLoop business logic."""

from __future__ import annotations

import asyncio
import re
from unittest.mock import ANY
from urllib.parse import urljoin

import pytest
from aioresponses import aioresponses
from httpx import AsyncClient
from safir.testing.slack import MockSlackWebhook

from mobu.config import config

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.jupyter import JupyterAction, JupyterState, MockJupyter
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, jupyter: MockJupyter, mock_aioresponses: aioresponses
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
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "max_executions": 3},
            },
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
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "gidnumber": 1000,
            "username": "testuser1",
        },
    }

    # Check that the lab is shut down properly between iterations.
    assert jupyter.state["testuser1"] == JupyterState.LOGGED_IN

    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Starting up" in r.text
    assert ": Server requested" in r.text
    assert ": Spawning server..." in r.text
    assert ": Ready" in r.text
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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {
                    "spawn_settle_time": 0,
                    "delete_lab": False,
                    "max_executions": 1,
                    "execution_idle_time": 0,
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["failure_count"] == 0

    # Check that the lab is still running between iterations.
    assert jupyter.state["testuser1"] == JupyterState.LAB_RUNNING


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
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "max_executions": 3},
            },
        },
    )
    assert r.status_code == 201

    # Wait for a second so that all the monkeys get started.
    await asyncio.sleep(1)

    # Now end the test without shutting anything down explicitly.  This tests
    # that server shutdown correctly stops everything and cleans up resources.


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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "delete_lab": False},
            },
        },
    )
    assert r.status_code == 201

    # End the test without shutting anything down and telling the mock
    # JupyterHub to take a while to shut down.  The test asgi-lifespan wrapper
    # has a shutdown timeout of ten seconds and delete will take five seconds,
    # so the test is that everything shuts down cleanly without throwing
    # exceptions.
    jupyter.delete_immediate = False


@pytest.mark.asyncio
async def test_hub_failed(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.fail("testuser2", JupyterAction.SPAWN)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "delete_lab": False},
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser2")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    assert config.environment_url
    url = urljoin(str(config.environment_url), "/nb/hub/spawn")
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Status 500 from POST {url}",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser2",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nspawn_lab",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Message*\nfoo",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_redirect_loop(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.redirect_loop = True

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "delete_lab": False},
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    assert config.environment_url
    url = urljoin(
        str(config.environment_url),
        "/nb/hub/api/users/testuser1/server/progress",
    )
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Status 303 from GET {url}",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nspawn_lab",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Message*\nTooManyRedirects",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_spawn_timeout(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.spawn_timeout = True

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "spawn_timeout": 1},
            },
        },
    )
    assert r.status_code == 201

    # Wait for one loop to finish.  We should finish with an error fairly
    # quickly (one second) and post a timeout alert to Slack.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Lab did not spawn after 1s",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nspawn_lab",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_spawn_failed(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.fail("testuser1", JupyterAction.PROGRESS)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {"spawn_settle_time": 0, "spawn_timeout": 1},
            },
        },
    )
    assert r.status_code == 201

    # Wait for one loop to finish.  We should finish with an error fairly
    # quickly (one second) and post a timeout alert to Slack.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Spawning lab failed",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nspawn_lab",
                            "verbatim": True,
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ANY, "verbatim": True},
                },
                {"type": "divider"},
            ],
        }
    ]
    log = slack.messages[0]["blocks"][2]["text"]["text"]
    log = re.sub(r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d(.\d\d\d)?", "<ts>", log)
    assert log == (
        "*Log*\n"
        "<ts> - Server requested\n"
        "<ts> - Spawning server...\n"
        "<ts> - Spawn failed!"
    )


@pytest.mark.asyncio
async def test_delete_timeout(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)
    jupyter.delete_immediate = False

    # Set delete_timeout to 1s even though we pause in increments of 2s since
    # this increases the chances we won't go slightly over to 4s.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {
                    "spawn_settle_time": 0,
                    "delete_timeout": 1,
                    "max_executions": 1,
                    "execution_idle_time": 0,
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait for one loop to finish.  We should finish with an error fairly
    # quickly (one second) and post a delete timeout alert to Slack.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Lab not deleted after 2s",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\ndelete_lab",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nRecommended (Weekly 2021_33)",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_code_exception(
    client: AsyncClient,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
                "options": {
                    "code": 'raise Exception("some error")',
                    "spawn_settle_time": 0,
                    "max_executions": 1,
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["failure_count"] == 1

    # Check that an appropriate error was posted.
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running code",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nexecute_code",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nRecommended (Weekly 2021_33)",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Node*\nsome-node",
                            "verbatim": True,
                        },
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
    error = slack.messages[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert "Exception: some error" in error


@pytest.mark.asyncio
async def test_long_error(
    client: AsyncClient,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "JupyterPythonLoop",
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
                    "max_executions": 1,
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "testuser1")
    assert data["business"]["failure_count"] == 1

    # Check that an appropriate error was posted.
    error = "... truncated ...\n"
    line = "this is a single line of output to test trimming errors"
    for i in range(5, 54):
        error += f"{line} #{i}\n"
    assert 2977 - len(line) <= len(error) <= 2977
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running code",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nexecute_code",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nd_2021_08_30",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Node*\nsome-node",
                            "verbatim": True,
                        },
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
