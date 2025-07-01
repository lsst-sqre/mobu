"""Tests for TAPQueryRunner."""

from __future__ import annotations

from typing import cast
from unittest.mock import ANY, patch

import pytest
import pyvo
import respx
from httpx import AsyncClient
from safir.metrics import NOT_NONE, MockEventPublisher

from mobu.events import Events

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, respx_mock: respx.Router, events: Events
) -> None:
    mock_gafaelfawr(respx_mock)
    queries = [
        "SELECT TOP 10 * FROM TAP_SCHEMA.tables",
        "SELECT TOP 10 * FROM TAP_SCHEMA.columns",
    ]

    with patch.object(pyvo.dal, "TAPService"):
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "TAPQueryRunner",
                    "options": {"queries": queries},
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "TAPQueryRunner",
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
        r = await client.get(
            "/mobu/flocks/test/monkeys/bot-mobu-testuser1/log"
        )
        assert r.status_code == 200
        assert "Running (sync): " in r.text
        found = False
        for query in queries:
            if query in r.text:
                found = True
        assert found, "Ran one of the appropriate queries"
        assert "Query finished after " in r.text

        published = cast("MockEventPublisher", events.tap_query).published
        published.assert_published_all(
            [
                {
                    "business": "TAPQueryRunner",
                    "duration": NOT_NONE,
                    "flock": "test",
                    "success": True,
                    "sync": True,
                    "username": "bot-mobu-testuser1",
                }
            ]
        )
