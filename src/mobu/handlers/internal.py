"""Internal HTTP handlers that serve relative to the root path, ``/``.

These handlers aren't externally visible since the app is available at a path,
``/mobu``. See `mobu.handlers.external` for the external endpoint handlers.

These handlers should be used for monitoring, health checks, internal status,
or other information that should not be visible outside the Kubernetes cluster.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from safir.metadata import Metadata, get_metadata
from safir.slack.webhook import SlackRouteErrorHandler

from ..config import Config
from ..dependencies.config import config_dependency

internal_router = APIRouter(route_class=SlackRouteErrorHandler)
"""FastAPI router for all internal handlers."""

__all__ = ["internal_router"]


@internal_router.get(
    "/",
    description=(
        "Return metadata about the running application. Can also be used as"
        " a health check. This route is not exposed outside the cluster and"
        " therefore cannot be used by external clients."
    ),
    response_model_exclude_none=True,
    summary="Application metadata",
)
async def get_index(
    config: Annotated[Config, Depends(config_dependency)],
) -> Metadata:
    return get_metadata(package_name="mobu", application_name=config.name)
