"""Tests for multi-instance logic."""

from typing import cast
from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient
from safir.metrics import MockEventPublisher

from mobu.events import Events

from .support.gafaelfawr import mock_gafaelfawr
from .support.util import wait_for_business


@pytest.mark.asyncio
@pytest.mark.usefixtures("_base_multi_instance")
async def test_good_user_config(
    client: AsyncClient,
    respx_mock: respx.Router,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up our mocked business
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "EmptyLoop",
            },
        },
    )

    assert r.status_code == 201

    # Wait until we've finished at least one loop,
    # then check the results.
    data = await wait_for_business(client, "bot-mobu-testuser-instance-2-1")
    assert data == {
        "name": "bot-mobu-testuser-instance-2-1",
        "business": {
            "failure_count": 0,
            "name": "EmptyLoop",
            "refreshing": False,
            "success_count": 1,
        },
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "bot-mobu-testuser-instance-2-1",
        },
    }

    # Check events
    published = cast("MockEventPublisher", events.empty_loop).published
    published.assert_published_all(
        [
            {
                "business": "EmptyLoop",
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser-instance-2-1",
            }
        ]
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_base_multi_instance")
async def test_bad_user_config(
    client: AsyncClient,
    respx_mock: respx.Router,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)

    # No uid_start or gid_start allowed
    with pytest.raises(RuntimeError, match="Only user_spec users"):
        await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "users": [
                    {
                        "username": "bot-mobu-someuser",
                    }
                ],
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "EmptyLoop",
                },
            },
        )

    # No uid_start or gid_start allowed
    with pytest.raises(RuntimeError, match="uid_start"):
        await client.put(
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
                    "type": "EmptyLoop",
                },
            },
        )
