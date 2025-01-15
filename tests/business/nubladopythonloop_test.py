"""Test the NubladoPythonLoop business logic."""

from __future__ import annotations

import asyncio
import re
from typing import cast
from unittest.mock import ANY
from urllib.parse import urljoin

import pytest
import respx
from anys import ANY_AWARE_DATETIME_STR, AnyContains, AnyWithEntries
from httpx import AsyncClient
from rubin.nublado.client.testing import (
    JupyterAction,
    JupyterState,
    MockJupyter,
)
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.sentry import Captured
from safir.testing.slack import MockSlackWebhook

from mobu.dependencies.config import config_dependency
from mobu.events import Events

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    events: Events,
) -> None:
    mock_gafaelfawr(
        respx_mock, username="bot-mobu-testuser1", uid=1000, gid=1000
    )

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {
                "username_prefix": "bot-mobu-testuser",
                "uid_start": 1000,
            },
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "max_executions": 3},
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.  Make sure nothing fails.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data == {
        "name": "bot-mobu-testuser1",
        "business": {
            "failure_count": 0,
            "name": "NubladoPythonLoop",
            "refreshing": False,
            "success_count": 1,
        },
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "gidnumber": 1000,
            "username": "bot-mobu-testuser1",
        },
    }

    # Check that the lab is shut down properly between iterations.
    assert jupyter.state["bot-mobu-testuser1"] == JupyterState.LOGGED_IN

    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200
    assert "Starting up" in r.text
    assert ": Server requested" in r.text
    assert ": Spawning server..." in r.text
    assert ": Ready" in r.text
    assert "Exception thrown" not in r.text

    r = await client.delete("/mobu/flocks/test")
    assert r.status_code == 204

    # Check events
    publisher = cast(MockEventPublisher, events.nublado_python_execution)
    published = publisher.published
    published.assert_published_all(
        [
            {
                "business": "NubladoPythonLoop",
                "code": 'print(2+2, end="")',
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            },
            {
                "business": "NubladoPythonLoop",
                "code": 'print(2+2, end="")',
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            },
            {
                "business": "NubladoPythonLoop",
                "code": 'print(2+2, end="")',
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            },
        ]
    )

    publisher = cast(MockEventPublisher, events.nublado_spawn_lab)
    published = publisher.published
    published.assert_published_all(
        [
            {
                "business": "NubladoPythonLoop",
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_reuse_lab(
    client: AsyncClient, jupyter: MockJupyter, respx_mock: respx.Router
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
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
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["failure_count"] == 0

    # Check that the lab is still running between iterations.
    assert jupyter.state["bot-mobu-testuser1"] == JupyterState.LAB_RUNNING


@pytest.mark.asyncio
async def test_server_shutdown(
    client: AsyncClient, respx_mock: respx.Router
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 20,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
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
async def test_delayed_delete(
    client: AsyncClient, jupyter: MockJupyter, respx_mock: respx.Router
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 5,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
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
    respx_mock: respx.Router,
    events: Events,
    sentry_items: Captured,
) -> None:
    config = config_dependency.config
    mock_gafaelfawr(respx_mock)
    jupyter.fail("bot-mobu-testuser2", JupyterAction.SPAWN)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 2,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "delete_lab": False},
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "bot-mobu-testuser2")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Confirm Sentry events
    (sentry_error,) = sentry_items.errors
    assert config.environment_url
    url = urljoin(str(config.environment_url), "/nb/hub/spawn")
    assert sentry_error["contexts"]["phase"] == {
        "phase": "spawn_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "JupyterWebError",
                "value": (f"Status 500 from POST {url}"),
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser2"}

    # Check events
    publisher = cast(MockEventPublisher, events.nublado_spawn_lab)
    published = publisher.published
    published.assert_published_all(
        [
            {
                "business": "NubladoPythonLoop",
                "duration": NOT_NONE,
                "flock": "test",
                "success": False,
                "username": "bot-mobu-testuser2",
            },
            {
                "business": "NubladoPythonLoop",
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            },
        ]
    )


@pytest.mark.asyncio
async def test_redirect_loop(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)
    jupyter.redirect_loop = True

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "delete_lab": False},
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "JupyterWebError",
                "value": (
                    "TooManyRedirects: Exceeded maximum allowed redirects."
                ),
            }
        )
    )
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["contexts"]["phase"] == {
        "phase": "spawn_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }

    (sentry_attachment,) = sentry_items.attachments
    assert sentry_attachment.filename == "spawn_log.txt"
    assert sentry_attachment.bytes.decode() == ""


@pytest.mark.asyncio
async def test_spawn_timeout(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)
    jupyter.spawn_timeout = True

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "spawn_timeout": 1},
            },
        },
    )
    assert r.status_code == 201

    # Wait for one loop to finish.  We should finish with an error fairly
    # quickly (one second) and post a timeout alert to Slack.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["phase"] == {
        "phase": "spawn_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "JupyterSpawnTimeoutError",
                "value": ("Lab did not spawn after 1s"),
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_attachment,) = sentry_items.attachments
    assert sentry_attachment.filename == "spawn_log.txt"


@pytest.mark.asyncio
async def test_spawn_failed(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)
    jupyter.fail("bot-mobu-testuser1", JupyterAction.PROGRESS)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "spawn_timeout": 1},
            },
        },
    )
    assert r.status_code == 201

    # Wait for one loop to finish.  We should finish with an error fairly
    # quickly (one second) and post a timeout alert to Slack.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["phase"] == {
        "phase": "spawn_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "JupyterSpawnError",
                "value": "",
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_attachment,) = sentry_items.attachments
    assert sentry_attachment.filename == "spawn_log.txt"

    log = re.sub(
        r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d(.\d\d\d)?",
        "<ts>",
        sentry_attachment.bytes.decode(),
    )
    assert log == (
        "<ts> - Server requested\n"
        "<ts> - Spawning server...\n"
        "<ts> - Spawn failed!"
    )


@pytest.mark.asyncio
async def test_delete_timeout(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)
    jupyter.delete_immediate = False

    # Set delete_timeout to 1s even though we pause in increments of 2s since
    # this increases the chances we won't go slightly over to 4s.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
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
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["success_count"] == 0
    assert data["business"]["failure_count"] > 0

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["phase"] == {
        "phase": "delete_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "JupyterDeleteTimeoutError",
                "value": "Lab not deleted after 2s",
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": "Recommended (Weekly 2077_43)",
        "node": None,
        "phase": "delete_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}


@pytest.mark.asyncio
async def test_code_exception(
    client: AsyncClient,
    respx_mock: respx.Router,
    events: Events,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
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
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["failure_count"] == 1

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["code_info"] == {
        "code": 'raise Exception("some error")'
    }
    assert sentry_error["contexts"]["phase"] == {
        "phase": "execute_code",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "CodeExecutionError",
                "value": "Code execution failed",
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": "Recommended (Weekly 2077_43)",
        "node": "Node1",
        "phase": "execute_code",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    # Check events
    publisher = cast(MockEventPublisher, events.nublado_python_execution)
    published = publisher.published
    published.assert_published_all(
        [
            {
                "business": "NubladoPythonLoop",
                "code": 'raise Exception("some error")',
                "duration": None,
                "flock": "test",
                "success": False,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_long_error(
    client: AsyncClient,
    jupyter: MockJupyter,
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "code": "long_error_for_test()",
                    "spawn_settle_time": 0,
                    "max_executions": 1,
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["failure_count"] == 1

    # Check the lab form.
    assert jupyter.lab_form["bot-mobu-testuser1"] == {
        "image_class": "recommended",
        "size": "Large",
    }

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "CodeExecutionError",
                "value": "Code execution failed",
            }
        )
    )
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": "Recommended (Weekly 2077_43)",
        "node": "Node1",
        "phase": "execute_code",
    }
    assert sentry_error["contexts"]["phase"] == {
        "phase": "execute_code",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["contexts"]["code_info"] == {
        "code": "long_error_for_test()"
    }

    # Check that an appropriate error attachment was captured.
    (sentry_attachment,) = sentry_items.attachments
    text = sentry_attachment.bytes.decode()
    error = ""
    line = "this is a single line of output to test trimming errors"
    for i in range(54):
        error += f"{line} #{i}\n"
    assert text == error


@pytest.mark.asyncio
async def test_lab_controller(
    client: AsyncClient, jupyter: MockJupyter, respx_mock: respx.Router
) -> None:
    mock_gafaelfawr(respx_mock)

    # Image by reference.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "users": [{"username": "bot-mobu-testuser"}],
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "image": {
                        "image_class": "by-reference",
                        "reference": (
                            "registry.hub.docker.com/lsstsqre/sciplat-lab"
                            ":d_2021_08_30"
                        ),
                    },
                },
            },
        },
    )
    assert r.status_code == 201
    await asyncio.sleep(0)
    assert jupyter.lab_form["bot-mobu-testuser"] == {
        "image_list": (
            "registry.hub.docker.com/lsstsqre/sciplat-lab:d_2021_08_30"
        ),
        "size": "Large",
    }
    r = await client.delete(r.headers["Location"])
    assert r.status_code == 204

    # Image by class.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "users": [{"username": "bot-mobu-testuser"}],
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "image": {
                        "image_class": "latest-daily",
                        "size": "Medium",
                        "debug": True,
                    },
                },
            },
        },
    )
    assert r.status_code == 201
    await asyncio.sleep(0)
    assert jupyter.lab_form["bot-mobu-testuser"] == {
        "enable_debug": "true",
        "image_class": "latest-daily",
        "size": "Medium",
    }
    r = await client.delete(r.headers["Location"])
    assert r.status_code == 204

    # Image by tag.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "users": [{"username": "bot-mobu-testuser"}],
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "image": {
                        "image_class": "by-tag",
                        "tag": "w_2077_44",
                        "size": "Small",
                    },
                },
            },
        },
    )
    assert r.status_code == 201
    await asyncio.sleep(0)
    assert jupyter.lab_form["bot-mobu-testuser"] == {
        "image_tag": "w_2077_44",
        "size": "Small",
    }


@pytest.mark.asyncio
async def test_ansi_error(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "code": (
                        'raise ValueError("\\033[38;5;28;01mFoo\\033[39;00m")'
                    ),
                    "image": {
                        "image_class": "by-reference",
                        "reference": (
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
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data["business"]["failure_count"] == 1

    # Check that an appropriate error was posted.
    (sentry_attachment,) = sentry_items.attachments
    error = sentry_attachment.bytes.decode()
    assert "ValueError: Foo" in error
    assert "\033" not in error

    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["code_info"] == {
        "code": 'raise ValueError("\\033[38;5;28;01mFoo\\033[39;00m")'
    }
    assert sentry_error["contexts"]["phase"] == {
        "phase": "execute_code",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {"type": "CodeExecutionError", "value": "Code execution failed"}
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image": "Recommended (Weekly 2077_43)",
        "node": "Node1",
        "phase": "execute_code",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}
