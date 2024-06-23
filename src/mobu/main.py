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
from contextlib import AsyncExitStack, asynccontextmanager
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
from .dependencies.context import ContextDependency, context_dependency
from .dependencies.github import (
    ci_manager_dependency,
    github_config_dependency,
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
async def base_lifespan(app: FastAPI) -> AsyncIterator[ContextDependency]:
    """Set up and tear down the the base application."""
    if not config.environment_url:
        raise RuntimeError("MOBU_ENVIRONMENT_URL was not set")
    if not config.gafaelfawr_token:
        raise RuntimeError("MOBU_GAFAELFAWR_TOKEN was not set")

    await context_dependency.initialize()
    await context_dependency.process_context.manager.autostart()

    status_interval = timedelta(days=1)
    app.state.periodic_status = schedule_periodic(post_status, status_interval)

    yield context_dependency

    await context_dependency.aclose()
    app.state.periodic_status.cancel()


@asynccontextmanager
async def github_ci_app_lifespan(
    base_context: ContextDependency,
) -> AsyncIterator[None]:
    """Set up and tear down the GitHub CI app functionality."""
    if not config.github_config_path:
        raise RuntimeError("MOBU_GITHUB_CONFIG_PATH was not set")
    if not config.github_ci_app.webhook_secret:
        raise RuntimeError("MOBU_GITHUB_CI_APP_WEBHOOK_SECRET was not set")
    if not config.github_ci_app.private_key:
        raise RuntimeError("MOBU_GITHUB_CI_APP_PRIVATE_KEY was not set")
    if not config.github_ci_app.id:
        raise RuntimeError("MOBU_GITHUB_CI_APP_ID was not set")

    github_config_dependency.initialize(config.github_config_path)
    ci_manager_dependency.initialize(
        base_context=base_context,
        users=github_config_dependency.config.users,
    )
    await ci_manager_dependency.ci_manager.start()

    yield

    await ci_manager_dependency.aclose()


@asynccontextmanager
async def github_refresh_app_lifespan() -> AsyncIterator[None]:
    """Set up and tear down the GitHub refresh app functionality."""
    if not config.github_config_path:
        raise RuntimeError("MOBU_GITHUB_CONFIG_PATH was not set")
    if not config.github_refresh_app.webhook_secret:
        raise RuntimeError(
            "MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET was not set"
        )
    github_config_dependency.initialize(config.github_config_path)

    yield


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set up and tear down the entire application.

    Conditionally sets up and tears down the different GitHub app
    integrations based on config settings.
    """
    async with AsyncExitStack() as stack:
        base_context = await stack.enter_async_context(base_lifespan(app))
        if config.github_ci_app.enabled:
            await stack.enter_async_context(
                github_ci_app_lifespan(base_context)
            )
        if config.github_refresh_app.enabled:
            await stack.enter_async_context(github_refresh_app_lifespan())

        yield


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

if config.github_ci_app.enabled:
    app.include_router(
        github_ci_app_router, prefix=f"{config.path_prefix}/github/ci"
    )
if config.github_refresh_app.enabled:
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
