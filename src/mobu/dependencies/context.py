"""Request context dependency for FastAPI.

This dependency gathers a variety of information into a single object for the
convenience of writing request handlers.  It also provides a place to store a
`structlog.BoundLogger` that can gather additional context during processing,
including from dependencies.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from safir.dependencies.gafaelfawr import auth_logger_dependency
from safir.dependencies.http_client import http_client_dependency
from safir.dependencies.logger import logger_dependency
from safir.metrics import EventManager
from structlog.stdlib import BoundLogger

from ..events import Events
from ..factory import Factory, ProcessContext
from ..services.manager import FlockManager
from ..services.repo import RepoManager

__all__ = [
    "ContextDependency",
    "RequestContext",
    "anonymous_context_dependency",
    "context_dependency",
]


@dataclass(slots=True)
class RequestContext:
    """Holds the incoming request and its surrounding context."""

    request: Request
    """Incoming request."""

    logger: BoundLogger
    """Request logger, rebound with discovered context."""

    manager: FlockManager
    """Global singleton flock manager."""

    repo_manager: RepoManager
    """Global singleton git repo manager."""

    factory: Factory
    """Component factory."""

    def rebind_logger(self, **values: Any) -> None:
        """Add the given values to the logging context.

        Parameters
        ----------
        **values
            Additional values that should be added to the logging context.
        """
        self.logger = self.logger.bind(**values)
        self.factory.set_logger(self.logger)


class ContextDependency:
    """Provide a per-request context as a FastAPI dependency.

    Each request gets a `RequestContext`.  To save overhead, the portions of
    the context that are shared by all requests are collected into the single
    process-global `~mobu.factory.ProcessContext` and reused with each
    request.
    """

    def __init__(self) -> None:
        self._process_context: ProcessContext | None = None

    async def __call__(
        self,
        request: Request,
        logger: Annotated[BoundLogger, Depends(auth_logger_dependency)],
    ) -> RequestContext:
        """Create a per-request context."""
        if not self._process_context:
            raise RuntimeError("ContextDependency not initialized")
        return RequestContext(
            request=request,
            logger=logger,
            manager=self._process_context.manager,
            repo_manager=self._process_context.repo_manager,
            factory=Factory(self._process_context, logger),
        )

    @property
    def process_context(self) -> ProcessContext:
        if not self._process_context:
            raise RuntimeError("ContextDependency not initialized")
        return self._process_context

    async def initialize(self, event_manager: EventManager) -> None:
        """Initialize the process-wide shared context."""
        if self._process_context:
            await self._process_context.aclose()
        http_client = await http_client_dependency()
        events = Events()
        self._process_context = ProcessContext(http_client, events)
        event_manager.logger = self.process_context.logger
        await events.initialize(event_manager)

    async def aclose(self) -> None:
        """Clean up the per-process configuration."""
        if self._process_context:
            await self._process_context.aclose()
        self._process_context = None


context_dependency = ContextDependency()
"""The dependency that will return the per-request context."""


async def anonymous_context_dependency(
    request: Request,
    logger: Annotated[BoundLogger, Depends(logger_dependency)],
) -> RequestContext:
    """Per-request context for non-gafaelfawr-auth'd requests."""
    return await context_dependency(request=request, logger=logger)
