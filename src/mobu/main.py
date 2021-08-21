"""The main application factory for the mobu service.

Notes
-----
Be aware that, following the normal pattern for FastAPI services, the app is
constructed when this module is loaded and is not deferred until a function is
called.
"""

from importlib.metadata import metadata

from aiohttp import ClientSession
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi_utils.tasks import repeat_every
from safir.logging import configure_logging
from safir.middleware.x_forwarded import XForwardedMiddleware

from .autostart import autostart
from .config import config
from .dependencies.manager import monkey_business_manager
from .exceptions import FlockNotFoundException, MonkeyNotFoundException
from .handlers.external import external_router
from .handlers.internal import internal_router
from .status import post_status

__all__ = ["app", "config"]


configure_logging(
    profile=config.profile,
    log_level=config.log_level,
    name=config.logger_name,
)

app = FastAPI()
"""The main FastAPI application for mobu."""

# Define the external routes in a subapp so that it will serve its own OpenAPI
# interface definition and documentation URLs under the external URL.
_subapp = FastAPI(
    title="mobu",
    description=metadata("mobu").get("Summary", ""),
    version=metadata("mobu").get("Version", "0.0.0"),
)
_subapp.include_router(external_router)

# Attach the internal routes and subapp to the main application.
app.include_router(internal_router)
app.mount(f"/{config.name}", _subapp)


@app.on_event("startup")
async def startup_event() -> None:
    if not config.environment_url:
        raise RuntimeError("ENVIRONMENT_URL was not set")
    app.add_middleware(XForwardedMiddleware)
    await monkey_business_manager.init()
    if config.autostart:
        await autostart()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await monkey_business_manager.cleanup()


@app.on_event("startup")
@repeat_every(seconds=60 * 60 * 24, wait_first=True)
async def periodic_status() -> None:
    async with ClientSession() as session:
        summaries = monkey_business_manager.summarize_flocks()
        await post_status(session, summaries)


@_subapp.exception_handler(FlockNotFoundException)
async def flock_not_found_exception_handler(
    request: Request, exc: FlockNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": [
                {
                    "loc": ["path", "flock"],
                    "msg": f"Flock for {exc.flock} not found",
                    "type": "flock_not_found",
                }
            ]
        },
    )


@_subapp.exception_handler(MonkeyNotFoundException)
async def monkey_not_found_exception_handler(
    request: Request, exc: MonkeyNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": [
                {
                    "loc": ["path", "monkey"],
                    "msg": f"Monkey for {exc.monkey} not found",
                    "type": "monkey_not_found",
                }
            ]
        },
    )
