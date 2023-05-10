"""Request context dependency for FastAPI.

This dependency gathers a variety of information into a single object for the
convenience of writing request handlers.  It also provides a place to store a
`structlog.BoundLogger` that can gather additional context during processing,
including from dependencies.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request
from safir.dependencies.gafaelfawr import auth_logger_dependency
from safir.dependencies.http_client import http_client_dependency
from structlog.stdlib import BoundLogger

from ..factory import Factory, ProcessContext
from ..services.manager import FlockManager

__all__ = [
    "ContextDependency",
    "RequestContext",
    "context_dependency",
]


@dataclass(slots=True)
class RequestContext:
    """Holds the incoming request and its surrounding context."""

    request: Request
    """Incoming request."""

    logger: BoundLogger
    """Request loger, rebound with discovered context."""

    manager: FlockManager
    """Global singleton flock manager."""

    factory: Factory
    """Component factory."""


class ContextDependency:
    """Provide a per-request context as a FastAPI dependency.

    Each request gets a `RequestContext`.  To save overhead, the portions of
    the context that are shared by all requests are collected into the single
    process-global `~mobu.factory.ProcessContext` and reused with each
    request.
    """

    def __init__(self) -> None:
        self._process_context: Optional[ProcessContext] = None

    async def __call__(
        self,
        request: Request,
        logger: BoundLogger = Depends(auth_logger_dependency),
    ) -> RequestContext:
        """Create a per-request context."""
        if not self._process_context:
            raise RuntimeError("ContextDependency not initialized")
        return RequestContext(
            request=request,
            logger=logger,
            manager=self._process_context.manager,
            factory=Factory(self._process_context, logger),
        )

    @property
    def process_context(self) -> ProcessContext:
        if not self._process_context:
            raise RuntimeError("ContextDependency not initialized")
        return self._process_context

    async def initialize(self) -> None:
        """Initialize the process-wide shared context."""
        if self._process_context:
            await self._process_context.aclose()
        http_client = await http_client_dependency()
        self._process_context = ProcessContext(http_client)

    async def aclose(self) -> None:
        """Clean up the per-process configuration."""
        if self._process_context:
            await self._process_context.aclose()
        self._process_context = None


context_dependency = ContextDependency()
"""The dependency that will return the per-request context."""
