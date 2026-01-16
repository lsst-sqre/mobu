"""Test the NubladoPythonLoop business logic."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import cast
from unittest.mock import ANY

import pytest
from anys import ANY_AWARE_DATETIME_STR, AnyContains, AnySearch, AnyWithEntries
from httpx import AsyncClient
from rubin.gafaelfawr import (
    GafaelfawrClient,
    GafaelfawrGroup,
    GafaelfawrUserInfo,
    MockGafaelfawr,
)
from rubin.nublado.client import (
    MockJupyter,
    MockJupyterAction,
    MockJupyterState,
)
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.sentry import Captured
from safir.testing.slack import MockSlackWebhook

from mobu.dependencies.config import config_dependency
from mobu.events import Events

from ..support.util import wait_for_business

# Use the Jupyter mock for all tests in this file.
pytestmark = pytest.mark.usefixtures("mock_jupyter")


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, mock_jupyter: MockJupyter, events: Events
) -> None:
    token = config_dependency.config.gafaelfawr_token
    gafaelfawr = GafaelfawrClient()

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

    # Check that the user was created with the correct parameters.
    userinfo = await gafaelfawr.get_user_info(token, "bot-mobu-testuser1")
    assert userinfo == GafaelfawrUserInfo(
        username="bot-mobu-testuser1",
        name="Mobu Test User",
        uid=1000,
        gid=1000,
    )

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
            "groups": [],
            "username": "bot-mobu-testuser1",
        },
    }

    # Check that the lab is shut down properly between iterations.
    state = mock_jupyter.get_state("bot-mobu-testuser1")
    assert state == MockJupyterState.LOGGED_IN

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
    publisher = cast("MockEventPublisher", events.nublado_python_execution)
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

    publisher = cast("MockEventPublisher", events.nublado_spawn_lab)
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
    client: AsyncClient, mock_jupyter: MockJupyter
) -> None:
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
    state = mock_jupyter.get_state("bot-mobu-testuser1")
    assert state == MockJupyterState.LAB_RUNNING


@pytest.mark.asyncio
async def test_server_shutdown(client: AsyncClient) -> None:
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
    client: AsyncClient, mock_jupyter: MockJupyter
) -> None:
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
    # JupyterHub to take a while to shut down. The test asgi-lifespan wrapper
    # has a shutdown timeout of ten seconds and delete will take five seconds,
    # so the test is that everything shuts down cleanly without throwing
    # exceptions.
    mock_jupyter.set_delete_delay(timedelta(seconds=5))


@pytest.mark.asyncio
async def test_hub_failed(
    client: AsyncClient,
    mock_jupyter: MockJupyter,
    events: Events,
    sentry_items: Captured,
) -> None:
    mock_jupyter.fail_on("bot-mobu-testuser2", MockJupyterAction.SPAWN)

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
    assert sentry_error["contexts"]["phase"] == {
        "phase": "spawn_lab",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "NubladoWebError",
                "value": AnySearch("Status 500 from POST https://"),
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "httpx_request_method": "POST",
        "httpx_request_url": ANY,
        "image_reference": None,
        "image_description": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser2"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - pre execute code"
    )

    # Check events
    publisher = cast("MockEventPublisher", events.nublado_spawn_lab)
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
async def test_spawn_timeout(
    client: AsyncClient, mock_jupyter: MockJupyter, sentry_items: Captured
) -> None:
    mock_jupyter.set_spawn_delay(timedelta(seconds=60))

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
        "image_reference": None,
        "image_description": None,
        "phase": "spawn_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_attachment,) = sentry_items.attachments
    assert sentry_attachment.filename == "spawn_log.txt"

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - pre execute code"
    )


@pytest.mark.asyncio
async def test_spawn_failed(
    client: AsyncClient, mock_jupyter: MockJupyter, sentry_items: Captured
) -> None:
    mock_jupyter.fail_on("bot-mobu-testuser1", MockJupyterAction.PROGRESS)

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
        "image_reference": None,
        "image_description": None,
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

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - pre execute code"
    )


@pytest.mark.asyncio
async def test_delete_timeout(
    client: AsyncClient, mock_jupyter: MockJupyter, sentry_items: Captured
) -> None:
    mock_jupyter.set_delete_delay(timedelta(seconds=5))

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
        "image_description": "Recommended (Weekly 2077_43)",
        "image_reference": "lighthouse.ceres/library/sketchbook:recommended",
        "node": None,
        "phase": "delete_lab",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - post execute code"
    )


@pytest.mark.asyncio
async def test_code_exception(
    client: AsyncClient,
    events: Events,
    sentry_items: Captured,
) -> None:
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
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "NubladoExecutionError",
                "value": "Code execution failed",
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image_description": "Recommended (Weekly 2077_43)",
        "image_reference": "lighthouse.ceres/library/sketchbook:recommended",
        "node": "Node1",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - Execute Python"
    )

    # Check events
    publisher = cast("MockEventPublisher", events.nublado_python_execution)
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
    mock_jupyter: MockJupyter,
    slack: MockSlackWebhook,
    sentry_items: Captured,
) -> None:
    error = ""
    line = "this is a single line of output to test trimming errors"
    for i in range(int(3000 / len(line))):
        error += f"{line} #{i}\n"
    code = f'msg = """{error}"""; raise ValueError(msg)'
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
                    "code": code,
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
    assert mock_jupyter.get_last_spawn_form("bot-mobu-testuser1") == {
        "image_class": "recommended",
        "size": "Large",
    }

    # Check that an appropriate error was posted.
    (sentry_error,) = sentry_items.errors
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "NubladoExecutionError",
                "value": "Code execution failed",
            }
        )
    )
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image_description": "Recommended (Weekly 2077_43)",
        "image_reference": "lighthouse.ceres/library/sketchbook:recommended",
        "node": "Node1",
    }
    assert sentry_error["contexts"]["code_info"] == {"code": code}

    # Check that the code and error are attached. These should be complete
    # even though they are long, unlike the Slack serialization.
    for sentry_attachment in sentry_items.attachments:
        assert sentry_attachment.filename in (
            "nublado_error.txt",
            "nublado_code.txt",
        )
        if sentry_attachment.filename == "nublado_error.txt":
            assert error in sentry_attachment.bytes.decode()
        elif sentry_attachment.filename == "nublado_code.txt":
            assert sentry_attachment.bytes.decode() == code

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - Execute Python"
    )


@pytest.mark.asyncio
async def test_lab_controller(
    client: AsyncClient, mock_jupyter: MockJupyter
) -> None:
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
                        "class": "by-reference",
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
    assert mock_jupyter.get_last_spawn_form("bot-mobu-testuser") == {
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
                        "class": "latest-daily",
                        "size": "Medium",
                        "debug": True,
                    },
                },
            },
        },
    )
    assert r.status_code == 201
    await asyncio.sleep(0)
    assert mock_jupyter.get_last_spawn_form("bot-mobu-testuser") == {
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
                        "class": "by-tag",
                        "tag": "w_2077_44",
                        "size": "Small",
                    },
                },
            },
        },
    )
    assert r.status_code == 201
    await asyncio.sleep(0)
    assert mock_jupyter.get_last_spawn_form("bot-mobu-testuser") == {
        "image_tag": "w_2077_44",
        "size": "Small",
    }


@pytest.mark.asyncio
async def test_ansi_error(
    client: AsyncClient, mock_jupyter: MockJupyter, sentry_items: Captured
) -> None:
    code = 'raise ValueError("\\033[38;5;28;01mFoo\\033[39;00m")'
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
                    "code": code,
                    "image": {
                        "class": "by-reference",
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
    for sentry_attachment in sentry_items.attachments:
        assert sentry_attachment.filename in (
            "nublado_error.txt",
            "nublado_code.txt",
        )
        if sentry_attachment.filename == "nublado_error.txt":
            error = sentry_attachment.bytes.decode()
            assert "ValueError: Foo" in error
            assert "\033" not in error
        elif sentry_attachment.filename == "nublado_code.txt":
            assert sentry_attachment.bytes.decode() == code

    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["code_info"] == {
        "code": 'raise ValueError("\\033[38;5;28;01mFoo\\033[39;00m")'
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {"type": "NubladoExecutionError", "value": "Code execution failed"}
        )
    )
    assert sentry_error["tags"] == {
        "business": "NubladoPythonLoop",
        "flock": "test",
        "image_description": "Recommended (Weekly 2077_43)",
        "image_reference": "lighthouse.ceres/library/sketchbook:recommended",
        "node": "Node1",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == (
        "NubladoPythonLoop - Execute Python"
    )


@pytest.mark.asyncio
async def test_user_spec_groups(
    client: AsyncClient,
    mock_jupyter: MockJupyter,
    mock_gafaelfawr: MockGafaelfawr,
    events: Events,
) -> None:
    gafaelfawr = GafaelfawrClient()
    token = config_dependency.config.gafaelfawr_token

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {
                "username_prefix": "bot-mobu-testuser",
                "uid_start": 1000,
                "groups": [{"name": "g_users", "id": 2000}],
            },
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {"spawn_settle_time": 0, "max_executions": 3},
            },
        },
    )
    assert r.status_code == 201

    # Check that the user was created with the correct parameters.
    userinfo = await gafaelfawr.get_user_info(token, "bot-mobu-testuser1")
    assert userinfo == GafaelfawrUserInfo(
        username="bot-mobu-testuser1",
        name="Mobu Test User",
        uid=1000,
        gid=1000,
        groups=[GafaelfawrGroup(name="g_users", id=2000)],
    )

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
            "groups": [{"name": "g_users", "id": 2000}],
            "username": "bot-mobu-testuser1",
        },
    }
