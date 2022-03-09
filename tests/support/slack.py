"""Mock Slack server for testing alerts."""

from __future__ import annotations

from typing import Any, Dict, List

from aioresponses import CallbackResult, aioresponses

from mobu.config import config


class MockSlack:
    """Represents a Slack incoming webhook and remembers what was posted."""

    def __init__(self) -> None:
        self.alerts: List[Dict[str, Any]] = []

    def alert(self, url: str, **kwargs: Any) -> CallbackResult:
        self.alerts.append(kwargs["json"])
        return CallbackResult(status=201)


def mock_slack(mocked: aioresponses) -> MockSlack:
    """Set up a mocked Slack server."""
    assert config.alert_hook
    mock = MockSlack()
    mocked.post(config.alert_hook, callback=mock.alert, repeat=True)
    return mock
