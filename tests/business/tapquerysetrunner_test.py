"""Tests for TAPQuerySetRunner."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import ANY, patch

import pytest
import pyvo
import respx
import structlog
import yaml
from httpx import AsyncClient
from safir.dependencies.http_client import http_client_dependency
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.slack import MockSlackWebhook

import mobu
from mobu.events import Events
from mobu.models.business.tapquerysetrunner import TAPQuerySetRunnerOptions
from mobu.models.user import AuthenticatedUser
from mobu.services.business.tapquerysetrunner import TAPQuerySetRunner

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, respx_mock: respx.Router, events: Events
) -> None:
    mock_gafaelfawr(respx_mock)

    with patch.object(pyvo.dal, "TAPService"):
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "TAPQuerySetRunner"},
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "TAPQuerySetRunner",
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }

        # Get the log and check that we logged the query.
        r = await client.get(
            "/mobu/flocks/test/monkeys/bot-mobu-testuser1/log"
        )
        assert r.status_code == 200
        assert "Running (sync): " in r.text
        assert "Query finished after " in r.text

    # Confirm metrics events
    published = cast(MockEventPublisher, events.tap_query).published
    published.assert_published_all(
        [
            {
                "business": "TAPQuerySetRunner",
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "sync": True,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_setup_error(
    client: AsyncClient,
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
) -> None:
    """Test that client creation is deferred to setup.

    This also doubles as a test that failures during setup are recorded as a
    failed test execution and result in a Slack alert.
    """
    mock_gafaelfawr(respx_mock)

    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "users": [{"username": "bot-mobu-tapuser"}],
            "scopes": ["exec:notebook"],
            "business": {"type": "TAPQuerySetRunner"},
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop and check the results.
    data = await wait_for_business(client, "bot-mobu-tapuser")
    assert data["business"]["failure_count"] == 1

    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "Unable to create TAP client: DALServiceError:"
                            " No working capabilities endpoint provided"
                        ),
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
                            "text": "*Exception type*\nTAPClientError",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\nbot-mobu-tapuser",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nmake_client",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Monkey*\ntest/bot-mobu-tapuser",
                            "verbatim": True,
                        },
                    ],
                },
                {"type": "divider"},
            ]
        }
    ]


@pytest.mark.asyncio
async def test_failure(
    client: AsyncClient,
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)

    with patch.object(pyvo.dal, "TAPService") as mock:
        mock.return_value.search.side_effect = [Exception("some error")]

        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "TAPQuerySetRunner"},
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data["business"]["failure_count"] == 1

    # Confirm metrics events
    published = cast(MockEventPublisher, events.tap_query).published
    published.assert_published_all(
        [
            {
                "business": "TAPQuerySetRunner",
                "duration": NOT_NONE,
                "flock": "test",
                "success": False,
                "sync": True,
                "username": "bot-mobu-testuser1",
            }
        ]
    )

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
                            "text": "*Exception type*\nCodeExecutionError",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\nbot-mobu-testuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nexecute_query",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Monkey*\ntest/bot-mobu-testuser1",
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
                                    "*Error*\n```\nException: some error\n```"
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
async def test_random_object(events: Events) -> None:
    for query_set in ("dp0.1", "dp0.2"):
        params_path = (
            Path(mobu.__file__).parent
            / "data"
            / "tapquerysetrunner"
            / query_set
            / "params.yaml"
        )
        with params_path.open("r") as f:
            objects = [str(o) for o in yaml.safe_load(f)["object_ids"]]

        user = AuthenticatedUser(
            username="bot-mobu-user", scopes=["read:tap"], token="blah blah"
        )
        logger = structlog.get_logger(__file__)
        options = TAPQuerySetRunnerOptions(query_set=query_set)
        http_client = await http_client_dependency()
        with patch.object(pyvo.dal, "TAPService"):
            runner = TAPQuerySetRunner(
                options=options,
                user=user,
                http_client=http_client,
                events=events,
                logger=logger,
                flock=None,
            )
        parameters = runner._generate_parameters()

        assert parameters["object"] in objects
        random_objects = cast(str, parameters["objects"]).split(", ")
        assert len(random_objects) == 12
        for obj in random_objects:
            assert obj in objects
