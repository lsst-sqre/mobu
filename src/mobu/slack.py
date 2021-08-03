"""Slack client for publishing alerts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .constants import DATE_FORMAT
from .exceptions import SlackError

if TYPE_CHECKING:
    from aiohttp import ClientSession

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

    def __init__(self, hook_url: str, session: ClientSession) -> None:
        self._hook_url = hook_url
        self._session = session

    async def alert(self, user: str, message: str) -> None:
        date = datetime.now().strftime(DATE_FORMAT)
        body = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": str(self),
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Date*\n{date}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*User*\n{user}",
                        },
                    ],
                },
            ],
        }
        await self._session.post(
            self._hook_url, json=body, raise_for_status=True
        )

    async def alert_from_exception(self, e: SlackError) -> None:
        await self._session.post(
            self._hook_url, json=e.to_slack(), raise_for_status=True
        )
