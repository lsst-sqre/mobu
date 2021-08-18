"""Tests for TAPQueryRunner."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import ANY, patch

import pytest
import pyvo

from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.util import wait_for_business

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient

    from tests.support.slack import MockSlack


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    with patch.object(pyvo.dal, "TAPService"):
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {
                    "username_prefix": "testuser",
                    "uid_start": 1000,
                },
                "scopes": ["exec:notebook"],
                "business": "TAPQueryRunner",
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "testuser1")
        assert data == {
            "name": "testuser1",
            "business": {
                "failure_count": 0,
                "name": "TAPQueryRunner",
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

        # Get the log and check that we logged the query.
        r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
        assert r.status_code == 200
        assert "Running: " in r.text
        assert "Query finished after " in r.text


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient, slack: MockSlack, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    with patch.object(pyvo.dal, "TAPService") as mock:
        mock.return_value.search.side_effect = [Exception("some error")]

        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {
                    "username_prefix": "testuser",
                    "uid_start": 1000,
                },
                "scopes": ["exec:notebook"],
                "business": "TAPQueryRunner",
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "testuser1")
        assert data["business"]["failure_count"] == 1

    assert slack.alerts == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running TAP query",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": "*User*\ntestuser1"},
                        {"type": "mrkdwn", "text": "*Event*\nexecute_query"},
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
                                "text": (
                                    "*Error*\n"
                                    "```\nException: some error\n```"
                                ),
                                "verbatim": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ANY,
                                "verbatim": True,
                            },
                        },
                    ]
                }
            ],
        }
    ]
