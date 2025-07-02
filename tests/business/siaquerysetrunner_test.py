"""Tests for SIAQuerySetRunner."""

from __future__ import annotations

from typing import cast
from unittest.mock import ANY, patch

import pytest
import pyvo
import respx
import structlog
from anys import ANY_AWARE_DATETIME_STR, AnyContains, AnySearch, AnyWithEntries
from httpx import AsyncClient
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.sentry import Captured

from mobu.events import Events
from mobu.models.business.siaquerysetrunner import SIAQuerySetRunnerOptions
from mobu.models.user import AuthenticatedUser
from mobu.services.business.siaquerysetrunner import SIAQuerySetRunner

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, respx_mock: respx.Router, events: Events
) -> None:
    mock_gafaelfawr(respx_mock)

    with patch.object(pyvo.dal, "SIA2Service"):
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "SIAQuerySetRunner"},
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "SIAQuerySetRunner",
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
        assert "Running SIA query: " in r.text
        assert "Query finished after " in r.text

    # Confirm metrics events
    published = cast("MockEventPublisher", events.sia_query).published
    published.assert_published_all(
        [
            {
                "business": "SIAQuerySetRunner",
                "duration": NOT_NONE,
                "flock": "test",
                "success": True,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_setup_error(
    client: AsyncClient,
    respx_mock: respx.Router,
    sentry_items: Captured,
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
            "users": [{"username": "bot-mobu-siauser"}],
            "scopes": ["exec:notebook"],
            "business": {"type": "SIAQuerySetRunner"},
        },
    )
    assert r.status_code == 201

    # Wait until we've finished at least one loop and check the results.
    data = await wait_for_business(client, "bot-mobu-siauser")
    assert data["business"]["failure_count"] == 1

    # Confirm Sentry events
    (sentry_error,) = sentry_items.errors

    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "DALServiceError",
                "value": "No working capabilities endpoint provided",
            }
        )
    )
    assert sentry_error["contexts"]["phase"] == {
        "phase": "make_client",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["tags"] == {
        "flock": "test",
        "business": "SIAQuerySetRunner",
        "phase": "make_client",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-siauser"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == "SIAQuerySetRunner - startup"


@pytest.mark.asyncio
async def test_failure(
    client: AsyncClient,
    respx_mock: respx.Router,
    events: Events,
    sentry_items: Captured,
) -> None:
    mock_gafaelfawr(respx_mock)
    with patch.object(pyvo.dal, "SIA2Service") as mock:
        mock.return_value.search.side_effect = [Exception("some error")]

        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {"type": "SIAQuerySetRunner"},
            },
        )
        assert r.status_code == 201

        # Wait until we've finished at least one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data["business"]["failure_count"] == 1

    # Confirm Sentry errors
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["phase"] == {
        "phase": "mobu.sia.search",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["contexts"]["query_info"] == {
        "started_at": ANY_AWARE_DATETIME_STR,
        "query": AnySearch("SIA parameters"),
    }
    assert sentry_error["tags"] == {
        "flock": "test",
        "business": "SIAQuerySetRunner",
        "phase": "mobu.sia.search",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_transaction,) = sentry_items.transactions
    assert sentry_transaction["transaction"] == "SIAQuerySetRunner - execute"

    # Confirm metrics events
    published = cast("MockEventPublisher", events.sia_query).published
    published.assert_published_all(
        [
            {
                "business": "SIAQuerySetRunner",
                "duration": NOT_NONE,
                "flock": "test",
                "success": False,
                "username": "bot-mobu-testuser1",
            }
        ]
    )


@pytest.mark.asyncio
async def test_random_object(events: Events) -> None:
    query_set = "dp02"
    user = AuthenticatedUser(
        username="bot-mobu-user", scopes=["read:image"], token="blah blah"
    )
    logger = structlog.get_logger(__file__)
    options = SIAQuerySetRunnerOptions(query_set=query_set)

    with patch.object(pyvo.dal, "SIA2Service"):
        runner = SIAQuerySetRunner(
            options=options,
            user=user,
            events=events,
            logger=logger,
            flock=None,
        )
    parameters = runner._generate_sia_params()
    assert parameters.ra >= 0.0
    assert parameters.ra <= 360.0
    assert parameters.dec >= -90.0
    assert parameters.dec <= 90.0
    assert parameters.radius >= 0.0
    assert parameters.radius <= 1.0
    assert parameters.pos == (parameters.ra, parameters.dec, parameters.radius)
    assert len(parameters.time) == 2
