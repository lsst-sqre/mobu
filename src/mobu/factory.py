"""Component factory and process-wide status for mobu."""

from __future__ import annotations

import structlog
from httpx import AsyncClient
from safir.slack.webhook import SlackWebhookClient
from structlog.stdlib import BoundLogger

from .config import config
from .models.solitary import SolitaryConfig
from .services.manager import FlockManager
from .services.solitary import Solitary
from .storage.gafaelfawr import GafaelfawrStorage

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
        self.logger = structlog.get_logger("mobu")
        self.gafaelfawr = GafaelfawrStorage(self.http_client, self.logger)
        self.manager = FlockManager(
            self.gafaelfawr, self.http_client, self.logger
        )

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
        self, context: ProcessContext, logger: BoundLogger | None = None
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
        if not config.alert_hook:
            return None
        return SlackWebhookClient(str(config.alert_hook), "Mobu", self._logger)

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
            solitary_config=solitary_config,
            gafaelfawr_storage=GafaelfawrStorage(
                self._context.http_client, self._logger
            ),
            http_client=self._context.http_client,
            logger=self._logger,
        )

    def set_logger(self, logger: BoundLogger) -> None:
        """Replace the internal logger.

        Used by the context dependency to update the logger for all
        newly-created components when it's rebound with additional context.

        Parameters
        ----------
        logger
            New logger.
        """
        self._logger = logger
