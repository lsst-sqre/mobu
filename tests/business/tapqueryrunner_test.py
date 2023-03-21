"""Tests for TAPQueryRunner."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import ANY, patch

import pytest
import pyvo
import structlog
import yaml
from aioresponses import aioresponses
from httpx import AsyncClient
from safir.testing.slack import MockSlackWebhook

import mobu
from mobu.models.business.tapqueryrunner import TAPQueryRunnerOptions
from mobu.models.user import AuthenticatedUser
from mobu.services.business.tapqueryrunner import TAPQueryRunner

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


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
                "user_spec": {"username_prefix": "testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "TAPQueryRunner"},
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
        assert "Running (sync): " in r.text
        assert "Query finished after " in r.text


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient,
    slack: MockSlackWebhook,
    mock_aioresponses: aioresponses,
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    with patch.object(pyvo.dal, "TAPService") as mock:
        mock.return_value.search.side_effect = [Exception("some error")]

        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "TAPQueryRunner"},
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "testuser1")
        assert data["business"]["failure_count"] == 1

    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running TAP query",
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
                            "text": "*Event*\nexecute_query",
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


@pytest.mark.asyncio
async def test_random_object() -> None:
    for query_set in ("dp0.1", "dp0.2"):
        params_path = (
            Path(mobu.__file__).parent
            / "data"
            / "tapqueryrunner"
            / query_set
            / "params.yaml"
        )
        with params_path.open("r") as f:
            objects = [str(o) for o in yaml.safe_load(f)["object_ids"]]

        user = AuthenticatedUser(
            username="user", scopes=["read:tap"], token="blah blah"
        )
        logger = structlog.get_logger(__file__)
        options = TAPQueryRunnerOptions(query_set=query_set)
        with patch.object(pyvo.dal, "TAPService"):
            runner = TAPQueryRunner(options, user, logger)
        parameters = runner._generate_parameters()

        assert parameters["object"] in objects
        random_objects = cast(str, parameters["objects"]).split(", ")
        assert len(random_objects) == 12
        for obj in random_objects:
            assert obj in objects
