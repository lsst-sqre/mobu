"""Mock Slack server for testing alerts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aioresponses import CallbackResult

from mobu.config import config

if TYPE_CHECKING:
    from typing import Any, Dict, List

    from aioresponses import aioresponses


class MockSlack:
    """Represents a Slack incoming webhook and remembers what was posted."""

    def __init__(self) -> None:
        self.alerts: List[Dict[str, Any]] = []

    def alert(self, url: str, **kwargs: Any) -> CallbackResult:
        self.alerts.append(kwargs["json"])
        return CallbackResult(status=201)


def mock_slack(mocked: aioresponses) -> MockSlack:
    """Set up a mocked Slack server."""
    mock = MockSlack()
    mocked.post(config.alert_hook, callback=mock.alert, repeat=True)
    return mock