"""Tests for GitLFS."""

from typing import cast
from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient
from safir.metrics import NOT_NONE, MockEventPublisher

from mobu.events import Events

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.gitlfs import flock_message
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient,
    respx_mock: respx.Router,
    gitlfs_mock: None,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up our mocked business
    r = await client.put("/mobu/flocks", json=flock_message)

    assert r.status_code == 201

    # Wait until we've finished at least one loop,
    # then check the results.

    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data == {
        "name": "bot-mobu-testuser1",
        "business": {
            "failure_count": 0,
            "name": "GitLFSBusiness",
            "refreshing": False,
            "success_count": 1,
        },
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "bot-mobu-testuser1",
            "groups": [],
        },
    }

    # Get the log and check that we logged the query.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200
    assert "Running Git-LFS check..." in r.text
    assert "Git-LFS check finished after " in r.text

    published = cast("MockEventPublisher", events.git_lfs_check).published
    published.assert_published_all(
        [
            {
                "business": "GitLFSBusiness",
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_fail(
    client: AsyncClient, respx_mock: respx.Router, events: Events
) -> None:
    mock_gafaelfawr(respx_mock)

    # Because we are not mocking the LFS calls, this will fail because there
    # is no Git LFS provider to connect to.

    r = await client.put("/mobu/flocks", json=flock_message)

    assert r.status_code == 201

    # Wait until we've finished at least one loop; check the results.
    # We expect it to have failed in the git push, because we don't really
    # have a Git LFS server for it to talk to.

    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data == {
        "name": "bot-mobu-testuser1",
        "business": {
            "failure_count": 1,
            "name": "GitLFSBusiness",
            "refreshing": False,
            "success_count": 0,
        },
        "state": ANY,
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "bot-mobu-testuser1",
            "groups": [],
        },
    }

    # Get the log and check that we logged the query.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200
    assert "Running Git-LFS check..." in r.text
    assert ("mobu.exceptions.SubprocessError") in r.text

    published = cast("MockEventPublisher", events.git_lfs_check).published
    published.assert_published_all(
        [
            {
                "business": "GitLFSBusiness",
                "duration": None,
                "flock": "test",
                "success": False,
                "username": "bot-mobu-testuser1",
            }
        ]
    )
