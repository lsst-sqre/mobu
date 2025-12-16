"""Tests for TAPQuerySetRunner."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import ANY, patch

import pytest
import pyvo
import structlog
import yaml
from anys import ANY_AWARE_DATETIME_STR, AnyContains, AnySearch, AnyWithEntries
from httpx import AsyncClient
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.sentry import Captured

import mobu
from mobu.events import Events
from mobu.models.business.tapquerysetrunner import TAPQuerySetRunnerOptions
from mobu.models.user import AuthenticatedUser
from mobu.services.business.tapquerysetrunner import TAPQuerySetRunner

from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(client: AsyncClient, events: Events) -> None:
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
        assert "Query finished after " in r.text

    # Confirm metrics events
    published = cast("MockEventPublisher", events.tap_query).published
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
    client: AsyncClient, sentry_items: Captured
) -> None:
    """Test that client creation is deferred to setup.

    This also doubles as a test that failures during setup are recorded as a
    failed test execution and result in a Slack alert.
    """
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

    # Confirm Sentry events
    (sentry_error,) = sentry_items.errors

    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "DALServiceError",
                "value": AnyContains("Cannot find TAP service"),
            }
        )
    )
    assert sentry_error["contexts"]["phase"] == {
        "phase": "make_client",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["tags"] == {
        "flock": "test",
        "business": "TAPQuerySetRunner",
        "phase": "make_client",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-tapuser"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == "TAPQuerySetRunner - startup"


@pytest.mark.asyncio
async def test_failure(
    client: AsyncClient, events: Events, sentry_items: Captured
) -> None:
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

    # Confirm Sentry errors
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["phase"] == {
        "phase": "mobu.tap.execute_query",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["contexts"]["query_info"] == {
        "started_at": ANY_AWARE_DATETIME_STR,
        "query": AnySearch("SELECT"),
    }
    assert sentry_error["tags"] == {
        "flock": "test",
        "business": "TAPQuerySetRunner",
        "phase": "mobu.tap.execute_query",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == "TAPQuerySetRunner - execute"

    # Confirm metrics events
    published = cast("MockEventPublisher", events.tap_query).published
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
        with patch.object(pyvo.dal, "TAPService"):
            runner = TAPQuerySetRunner(
                options=options,
                user=user,
                events=events,
                logger=logger,
                flock=None,
            )
        parameters = runner._generate_parameters()

        assert parameters["object"] in objects
        random_objects = cast("str", parameters["objects"]).split(", ")
        assert len(random_objects) == 12
        for obj in random_objects:
            assert obj in objects
