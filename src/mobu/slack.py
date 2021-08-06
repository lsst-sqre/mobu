"""Slack client for publishing alerts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from .constants import DATE_FORMAT
from .exceptions import SlackError

if TYPE_CHECKING:
    from typing import Any, Dict

    from aiohttp import ClientSession
    from structlog import BoundLogger

__all__ = ["SlackClient"]


class SlackClient:
    """Publish alerts via Slack.

    Uses an incoming webhook to publish an alert (from an exception) to a
    Slack channel.

    Parameters
    ----------
    hook_url : `str`
        The URL of the incoming webhook to use to publish the message.
    """

    def __init__(
        self, hook_url: str, session: ClientSession, logger: BoundLogger
    ) -> None:
        self._hook_url = hook_url
        self._session = session
        self._logger = logger

    async def alert(self, user: str, message: str) -> None:
        date = datetime.now().strftime(DATE_FORMAT)
        body = {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Date*\n{date}"},
                        {"type": "mrkdwn", "text": f"*User*\n{user}"},
                    ],
                },
            ]
        }
        await self._post_alert(body)

    async def alert_from_exception(self, e: SlackError) -> None:
        await self._post_alert(e.to_slack())

    async def _post_alert(self, alert: Dict[str, Any]) -> None:
        self._logger.info("Sending alert to Slack")
        try:
            await self._session.post(
                self._hook_url, json=alert, raise_for_status=True
            )
        except Exception:
            self._logger.exception("Posting alert to Slack failed")
            json_body = json.dumps(alert)
            self._logger.warning(f"Attempted alert body: {json_body}")
