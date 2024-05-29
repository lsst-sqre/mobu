"""The main application factory for the mobu service.

Notes
-----
Be aware that, following the normal pattern for FastAPI services, the app is
constructed when this module is loaded and is not deferred until a function is
called.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from importlib.metadata import metadata, version

import structlog
from fastapi import FastAPI
from safir.fastapi import ClientRequestError, client_request_error_handler
from safir.logging import Profile, configure_logging, configure_uvicorn_logging
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.slack.webhook import SlackRouteErrorHandler

from .asyncio import schedule_periodic
from .config import config
from .dependencies.context import context_dependency
from .handlers.external import external_router
from .handlers.github import github_router
from .handlers.internal import internal_router
from .status import post_status

__all__ = ["app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set up and tear down the the application."""
    if not config.environment_url:
        raise RuntimeError("MOBU_ENVIRONMENT_URL was not set")
    if not config.gafaelfawr_token:
        raise RuntimeError("MOBU_GAFAELFAWR_TOKEN was not set")
    await context_dependency.initialize()
    await context_dependency.process_context.manager.autostart()
    status_interval = timedelta(days=1)
    app.state.periodic_status = schedule_periodic(post_status, status_interval)

    yield

    await context_dependency.aclose()
    app.state.periodic_status.cancel()


configure_logging(
    name="mobu", profile=config.profile, log_level=config.log_level
)
if config.profile == Profile.production:
    configure_uvicorn_logging(config.log_level)

app = FastAPI(
    title="mobu",
    description=metadata("mobu")["Summary"],
    version=version("mobu"),
    openapi_url=f"{config.path_prefix}/openapi.json",
    docs_url=f"{config.path_prefix}/docs",
    redoc_url=f"{config.path_prefix}/redoc",
    lifespan=lifespan,
)
"""The main FastAPI application for mobu."""

# Attach the routers.
app.include_router(internal_router)
app.include_router(external_router, prefix=config.path_prefix)
app.include_router(github_router, prefix=f"{config.path_prefix}/github")

# Add middleware.
app.add_middleware(XForwardedMiddleware)

# Enable Slack alerting for uncaught exceptions.
if config.alert_hook:
    logger = structlog.get_logger("mobu")
    SlackRouteErrorHandler.initialize(str(config.alert_hook), "mobu", logger)
    logger.debug("Initialized Slack webhook")

# Enable the generic exception handler for client errors.
app.exception_handler(ClientRequestError)(client_request_error_handler)
