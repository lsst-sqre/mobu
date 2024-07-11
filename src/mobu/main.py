"""The main application factory for the mobu service.

Notes
-----
Be aware that, following the normal pattern for FastAPI services, the app is
constructed when this module is loaded and is not deferred until a function is
called.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from importlib.metadata import metadata, version

import structlog
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from safir.fastapi import ClientRequestError, client_request_error_handler
from safir.logging import Profile, configure_logging, configure_uvicorn_logging
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.slack.webhook import SlackRouteErrorHandler

from .asyncio import schedule_periodic
from .config import config
from .dependencies.context import context_dependency
from .dependencies.github import (
    ci_manager_dependency,
    github_ci_app_config_dependency,
    github_refresh_app_config_dependency,
)
from .handlers.external import external_router
from .handlers.github_ci_app import api_router as github_ci_app_router
from .handlers.github_refresh_app import (
    api_router as github_refresh_app_router,
)
from .handlers.internal import internal_router
from .status import post_status

__all__ = ["app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set up and tear down the the base application."""
    if not config.environment_url:
        raise RuntimeError("MOBU_ENVIRONMENT_URL was not set")
    if not config.gafaelfawr_token:
        raise RuntimeError("MOBU_GAFAELFAWR_TOKEN was not set")

    await context_dependency.initialize()
    await context_dependency.process_context.manager.autostart()

    status_interval = timedelta(days=1)
    app.state.periodic_status = schedule_periodic(post_status, status_interval)

    if config.github_refresh_app_config_path:
        github_refresh_app_config_dependency.initialize(
            config.github_refresh_app_config_path
        )

    if config.github_ci_app_config_path:
        github_ci_app_config_dependency.initialize(
            config.github_ci_app_config_path
        )
        ci_app_config = github_ci_app_config_dependency.config

        ci_manager_dependency.initialize(
            base_context=context_dependency,
            github_app_id=ci_app_config.id,
            github_private_key=ci_app_config.private_key,
            scopes=ci_app_config.scopes,
            users=ci_app_config.users,
        )
        await ci_manager_dependency.ci_manager.start()

    yield

    await ci_manager_dependency.aclose()
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

if config.github_ci_app_config_path:
    app.include_router(
        github_ci_app_router, prefix=f"{config.path_prefix}/github/ci"
    )

if config.github_refresh_app_config_path:
    app.include_router(
        github_refresh_app_router,
        prefix=f"{config.path_prefix}/github/refresh",
    )

# Add middleware.
app.add_middleware(XForwardedMiddleware)

# Enable Slack alerting for uncaught exceptions.
if config.alert_hook:
    logger = structlog.get_logger("mobu")
    SlackRouteErrorHandler.initialize(str(config.alert_hook), "mobu", logger)
    logger.debug("Initialized Slack webhook")

# Enable the generic exception handler for client errors.
app.exception_handler(ClientRequestError)(client_request_error_handler)


def create_openapi() -> str:
    """Create the OpenAPI spec for static documentation."""
    return json.dumps(
        get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    )
