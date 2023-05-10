"""The main application factory for the mobu service.

Notes
-----
Be aware that, following the normal pattern for FastAPI services, the app is
constructed when this module is loaded and is not deferred until a function is
called.
"""

import asyncio
from importlib.metadata import metadata, version

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from safir.logging import Profile, configure_logging, configure_uvicorn_logging
from safir.middleware.x_forwarded import XForwardedMiddleware
from safir.models import ErrorLocation
from safir.slack.webhook import SlackRouteErrorHandler

from .asyncio import schedule_periodic
from .config import config
from .dependencies.context import context_dependency
from .exceptions import FlockNotFoundException, MonkeyNotFoundException
from .handlers.external import external_router
from .handlers.internal import internal_router
from .status import post_status

__all__ = ["app", "config"]


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
)
"""The main FastAPI application for mobu."""

# Attach the routers.
app.include_router(internal_router)
app.include_router(external_router, prefix=config.path_prefix)

# Add middleware.
app.add_middleware(XForwardedMiddleware)

# Enable Slack alerting for uncaught exceptions.
if config.alert_hook:
    logger = structlog.get_logger("mobu")
    SlackRouteErrorHandler.initialize(config.alert_hook, "mobu", logger)
    logger.debug("Initialized Slack webhook")


@app.on_event("startup")
async def startup_event() -> None:
    if not config.environment_url:
        raise RuntimeError("ENVIRONMENT_URL was not set")
    if not config.gafaelfawr_token:
        raise RuntimeError("GAFAELFAWR_TOKEN was not set")
    await context_dependency.initialize()
    await context_dependency.process_context.manager.autostart()
    app.state.periodic_status = schedule_periodic(post_status, 60 * 60 * 24)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await context_dependency.aclose()
    app.state.periodic_status.cancel()
    try:
        await app.state.periodic_status
    except asyncio.CancelledError:
        pass


@app.exception_handler(FlockNotFoundException)
async def flock_not_found_exception_handler(
    request: Request, exc: FlockNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": [
                {
                    "loc": [ErrorLocation.path, "flock"],
                    "msg": f"Flock for {exc.flock} not found",
                    "type": "flock_not_found",
                }
            ]
        },
    )


@app.exception_handler(MonkeyNotFoundException)
async def monkey_not_found_exception_handler(
    request: Request, exc: MonkeyNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": [
                {
                    "loc": [ErrorLocation.path, "monkey"],
                    "msg": f"Monkey for {exc.monkey} not found",
                    "type": "monkey_not_found",
                }
            ]
        },
    )
