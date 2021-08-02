"""Slack client for publishing alerts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .constants import DATE_FORMAT

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

    async def alert(self, msg: str, name: str) -> None:
        time = datetime.now().strftime(DATE_FORMAT)
        alert_msg = f"{time} {name} {msg}"
        alert = {"text": alert_msg}
        await self._session.post(
            self._hook_url, json=alert, raise_for_status=True
        )
