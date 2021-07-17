"""The main application factory for the mobu service.

Notes
-----
Be aware that, following the normal pattern for FastAPI services, the app is
constructed when this module is loaded and is not deferred until a function is
called.
"""

from importlib.metadata import metadata

from fastapi import FastAPI
from safir.logging import configure_logging
from safir.middleware.x_forwarded import XForwardedMiddleware

from .config import config
from .dependencies.manager import monkey_business_manager
from .handlers.external import external_router
from .handlers.internal import internal_router

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
    app.add_middleware(XForwardedMiddleware)
    manager = await monkey_business_manager()
    await manager.init()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    manager = await monkey_business_manager()
    await manager.cleanup()
