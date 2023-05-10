"""Component factory and process-wide status for mobu."""

from __future__ import annotations

from typing import Optional

import structlog
from httpx import AsyncClient
from safir.slack.webhook import SlackWebhookClient
from structlog.stdlib import BoundLogger

from .config import config
from .models.solitary import SolitaryConfig
from .services.manager import FlockManager
from .services.solitary import Solitary

__all__ = ["Factory", "ProcessContext"]


class ProcessContext:
    """Per-process application context.

    This object caches all of the per-process singletons that can be reused
    for every request.

    Parameters
    ----------
    http_client
        Shared HTTP client.

    Attributes
    ----------
    http_client
        Shared HTTP client.
    manager
        Manager for all running flocks.
    """

    def __init__(self, http_client: AsyncClient) -> None:
        self.http_client = http_client
        self.manager = FlockManager(http_client, structlog.get_logger("mobu"))

    async def aclose(self) -> None:
        """Clean up a process context.

        Called before shutdown to free resources.
        """
        await self.manager.aclose()


class Factory:
    """Component factory for mobu.

    Uses the contents of a `ProcessContext` to construct the components of an
    application on demand.

    Parameters
    ----------
    context
        Shared process context.
    """

    def __init__(
        self, context: ProcessContext, logger: Optional[BoundLogger] = None
    ) -> None:
        self._context = context
        self._logger = logger if logger else structlog.get_logger("mobu")

    def create_slack_webhook_client(self) -> SlackWebhookClient | None:
        """Create a Slack webhook client if configured for Slack alerting.

        Returns
        -------
        SlackWebhookClient or None
            Newly-created Slack client, or `None` if Slack alerting is not
            configured.
        """
        if not config.alert_hook or config.alert_hook == "None":
            return None
        return SlackWebhookClient(config.alert_hook, "Mobu", self._logger)

    def create_solitary(self, solitary_config: SolitaryConfig) -> Solitary:
        """Create a runner for a solitary monkey.

        Parameters
        ----------
        solitary_config
            Configuration for the solitary monkey.

        Returns
        -------
        Solitary
            Newly-created solitary manager.
        """
        return Solitary(
            solitary_config, self._context.http_client, self._logger
        )
