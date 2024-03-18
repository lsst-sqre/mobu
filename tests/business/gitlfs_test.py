"""Tests for GitLFS."""

from unittest.mock import ANY, patch

import pytest
import respx
from httpx import AsyncClient

from mobu.services.business.gitlfs import GitLFSBusiness

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.gitlfs import (
    flock_message,
    no_git_lfs_data,
    uninstall_git_lfs,
    verify_uuid_contents,
)
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(client: AsyncClient, respx_mock: respx.Router) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up our mocked business
    with patch.object(
        GitLFSBusiness,
        "_install_git_lfs",
        side_effect=uninstall_git_lfs,
        autospec=True,
    ):
        with patch.object(
            GitLFSBusiness,
            "_check_uuid_pointer",
            side_effect=verify_uuid_contents,
            autospec=True,
        ):
            with patch.object(
                GitLFSBusiness,
                "_add_git_lfs_data",
                side_effect=no_git_lfs_data,
                autospec=True,
            ):
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
