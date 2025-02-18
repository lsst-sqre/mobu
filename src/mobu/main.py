"""The main application factory for the mobu service."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
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

from mobu.sentry import sentry_init

from .asyncio import schedule_periodic
from .dependencies.config import config_dependency
from .dependencies.context import context_dependency
from .dependencies.github import ci_manager_dependency
from .handlers.external import external_router
from .handlers.github_ci_app import api_router as github_ci_app_router
from .handlers.github_refresh_app import (
    api_router as github_refresh_app_router,
)
from .handlers.internal import internal_router
from .status import post_status

__all__ = ["create_app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Set up and tear down the the base application."""
    config = config_dependency.config
    if not config.environment_url:
        raise RuntimeError("MOBU_ENVIRONMENT_URL was not set")
    if not config.gafaelfawr_token:
        raise RuntimeError("MOBU_GAFAELFAWR_TOKEN was not set")

    event_manager = config.metrics.make_manager()
    await event_manager.initialize()
    await context_dependency.initialize(event_manager)

    await context_dependency.process_context.manager.autostart()

    status_interval = timedelta(days=1)
    app.state.periodic_status = schedule_periodic(post_status, status_interval)

    if config.github_ci_app:
        ci_manager_dependency.initialize(
            base_context=context_dependency,
            github_app_id=config.github_ci_app.id,
            github_private_key=config.github_ci_app.private_key,
            scopes=config.github_ci_app.scopes,
            users=config.github_ci_app.users,
        )
        await ci_manager_dependency.ci_manager.start()

    yield

    await ci_manager_dependency.aclose()
    await context_dependency.aclose()
    app.state.periodic_status.cancel()


def create_app(*, load_config: bool = True) -> FastAPI:
    """Create the FastAPI application.

    This is in a function rather than using a global variable (as is more
    typical for FastAPI) because some routing depends on configuration
    settings and we therefore want to recreate the application between tests.

    Parameters
    ----------
    load_config
        If set to `False`, do not try to load the configuration. This is used
        primarily for OpenAPI schema generation, where constructing the app is
        required but the configuration won't matter.
    """
    if load_config:
        config = config_dependency.config

        # Initialize Sentry.
        sentry_init(
            dsn=config.sentry_dsn,
            env=config.sentry_environment,
            traces_sample_config=config.sentry_traces_sample_config,
        )

        # Configure logging.
        configure_logging(
            name="mobu", profile=config.profile, log_level=config.log_level
        )
        if config.profile == Profile.production:
            configure_uvicorn_logging(config.log_level)

        # Enable Slack alerting for uncaught exceptions.
        if config.slack_alerts and config.alert_hook:
            logger = structlog.get_logger("mobu")
            SlackRouteErrorHandler.initialize(
                config.alert_hook, "mobu", logger
            )
            logger.debug("Initialized Slack webhook")

        path_prefix = config.path_prefix
        github_ci_app = config.github_ci_app
        github_refresh_app = config.github_refresh_app
    else:
        path_prefix = "/mobu"
        github_ci_app = None
        github_refresh_app = None

    app = FastAPI(
        title="mobu",
        description=metadata("mobu")["Summary"],
        version=version("mobu"),
        openapi_url=f"{path_prefix}/openapi.json",
        docs_url=f"{path_prefix}/docs",
        redoc_url=f"{path_prefix}/redoc",
        lifespan=lifespan,
    )

    # Attach the routers.
    app.include_router(internal_router)
    app.include_router(external_router, prefix=path_prefix)

    if github_ci_app:
        app.include_router(
            github_ci_app_router, prefix=f"{path_prefix}/github/ci"
        )

    if github_refresh_app:
        app.include_router(
            github_refresh_app_router,
            prefix=f"{config.path_prefix}/github/refresh",
        )

    # Add middleware.
    app.add_middleware(XForwardedMiddleware)

    # Enable the generic exception handler for client errors.
    app.exception_handler(ClientRequestError)(client_request_error_handler)

    return app


def create_openapi() -> str:
    """Create the OpenAPI spec for static documentation."""
    app = create_app(load_config=False)
    return json.dumps(
        get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    )
