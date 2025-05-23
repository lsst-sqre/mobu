"""Tests for ``post_status``."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from rubin.nublado.client.testing import MockJupyter
from safir.testing.slack import MockSlackWebhook

from mobu.models.flock import FlockSummary
from mobu.services.manager import FlockManager
from mobu.status import post_status


@pytest.mark.asyncio
async def test_post_status(
    client: AsyncClient, slack: MockSlackWebhook, jupyter: MockJupyter
) -> None:
    # If there are no flocks, no message should be posted.
    with patch.object(FlockManager, "summarize_flocks") as mock:
        mock.return_value = []
        await post_status()
        assert slack.messages == []

    # Check with some actual flock data.
    with patch.object(FlockManager, "summarize_flocks") as mock:
        mock.return_value = [
            FlockSummary(
                name="notebook",
                business="NotebookRunnerCounting",
                start_time=datetime(2021, 8, 20, 17, 3, tzinfo=UTC),
                monkey_count=5,
                success_count=487,
                failure_count=3,
            ),
            FlockSummary(
                name="tap",
                business="TAPQueryRunner",
                start_time=datetime(2021, 8, 20, 12, 40, tzinfo=UTC),
                monkey_count=1,
                success_count=200000,
                failure_count=1,
            ),
            FlockSummary(
                name="login",
                business="JupyterPythonLoop",
                start_time=None,
                monkey_count=2,
                success_count=0,
                failure_count=0,
            ),
        ]

        await post_status()

    expected = """\
Currently running 3 flocks against https://example.com:
• *notebook*: 5 monkeys started 2021-08-20 with 3 failures (99.39% success)
• *tap*: 1 monkey started 2021-08-20 with 1 failure (99.99% success)
• *login*: 2 monkeys (not started) with 0 failures (100.00% success)
"""
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": expected.strip(),
                        "verbatim": True,
                    },
                }
            ]
        }
    ]
