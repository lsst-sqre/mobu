"""Tests for ``post_status``."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from mobu.dependencies.manager import monkey_business_manager
from mobu.models.flock import FlockSummary
from mobu.status import post_status
from tests.support.slack import MockSlack


@pytest.mark.asyncio
async def test_post_status(slack: MockSlack) -> None:
    with patch.object(monkey_business_manager, "summarize_flocks") as mock:
        mock.return_value = [
            FlockSummary(
                name="notebook",
                business="NotebookRunner",
                start_time=datetime(2023, 2, 3, 16, 29, tzinfo=timezone.utc),
                monkey_count=5,
                success_count=487,
                failure_count=3,
            ),
            FlockSummary(
                name="tap",
                business="TAPQueryRunner",
                start_time=datetime(2023, 2, 3, 16, 33, tzinfo=timezone.utc),
                monkey_count=1,
                success_count=200000,
                failure_count=1,
            ),
            FlockSummary(
                name="login",
                business="JupyterLoginLoop",
                start_time=None,
                monkey_count=2,
                success_count=0,
                failure_count=0,
            ),
        ]

        await post_status()

    expected = """\
Currently running 3 flocks against https://test.example.com:
• *notebook*: 5 monkeys started 2023-02-03 with 3 failures (99.39% success)
• *tap*: 1 monkey started 2023-02-03 with 1 failure (99.99% success)
• *login*: 2 monkeys (not started) with 0 failures (100.00% success)
"""
    assert slack.alerts == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": expected},
                }
            ]
        }
    ]
