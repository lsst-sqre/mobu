"""Tests for GitLFS."""

from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.gitlfs import flock_message
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, respx_mock: respx.Router, gitlfs_mock: None
) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up our mocked business
    r = await client.put("/mobu/flocks", json=flock_message)

    assert r.status_code == 201

    # Wait until we've finished at least one loop,
    # then check the results.

    data = await wait_for_business(client, "testuser1")
    assert data == {
        "name": "testuser1",
        "business": {
            "failure_count": 0,
            "name": "GitLFSBusiness",
            "success_count": 1,
            "timings": ANY,
        },
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "testuser1",
        },
    }

    # Get the log and check that we logged the query.
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Running Git-LFS check..." in r.text
    assert "Git-LFS check finished after " in r.text


@pytest.mark.asyncio
async def test_fail(client: AsyncClient, respx_mock: respx.Router) -> None:
    mock_gafaelfawr(respx_mock)

    # Because we are not mocking the LFS calls, this will fail because there
    # is no Git LFS provider to connect to.

    r = await client.put("/mobu/flocks", json=flock_message)

    assert r.status_code == 201

    # Wait until we've finished at least one loop; check the results.
    # We expect it to have failed in the git push, because we don't really
    # have a Git LFS server for it to talk to.

    data = await wait_for_business(client, "testuser1")
    assert data == {
        "name": "testuser1",
        "business": {
            "failure_count": 1,
            "name": "GitLFSBusiness",
            "success_count": 0,
            "timings": ANY,
        },
        "state": ANY,
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "testuser1",
        },
    }

    # Get the log and check that we logged the query.
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "Running Git-LFS check..." in r.text
    assert ("mobu.exceptions.SubprocessError") in r.text
