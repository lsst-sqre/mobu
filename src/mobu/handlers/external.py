"""Handlers for the app's external root, ``/mobu/``."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from safir.datetime import current_datetime
from safir.metadata import get_metadata
from safir.models import ErrorModel
from safir.slack.webhook import SlackRouteErrorHandler

from ..config import config
from ..dependencies.context import RequestContext, context_dependency
from ..models.flock import FlockConfig, FlockData, FlockSummary
from ..models.index import Index
from ..models.monkey import MonkeyData
from ..models.solitary import SolitaryConfig, SolitaryResult

external_router = APIRouter(route_class=SlackRouteErrorHandler)
"""FastAPI router for all external handlers."""

__all__ = ["external_router"]


class FormattedJSONResponse(JSONResponse):
    """The same as ``fastapi.JSONResponse`` except formatted for humans."""

    def render(self, content: Any) -> bytes:
        """Render a data structure into JSON formatted for humans."""
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=4,
            sort_keys=True,
        ).encode()


@external_router.get(
    "/",
    description=("Metadata about the running version of mobu"),
    response_model=Index,
    response_model_exclude_none=True,
    summary="Application metadata",
)
async def get_index() -> Index:
    metadata = get_metadata(
        package_name="mobu",
        application_name=config.name,
    )
    return Index(metadata=metadata)


@external_router.get(
    "/flocks", response_model=list[str], summary="List running flocks"
)
async def get_flocks(
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> list[str]:
    return context.manager.list_flocks()


@external_router.put(
    "/flocks",
    response_class=FormattedJSONResponse,
    response_model=FlockData,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    status_code=201,
    summary="Create a new flock",
)
async def put_flock(
    flock_config: FlockConfig,
    response: Response,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> FlockData:
    context.logger.info(
        "Creating flock",
        flock=flock_config.name,
        config=flock_config.model_dump(exclude_unset=True),
    )
    flock = await context.manager.start_flock(flock_config)
    flock_url = context.request.url_for("get_flock", flock=flock.name)
    response.headers["Location"] = str(flock_url)
    return flock.dump()


@external_router.get(
    "/flocks/{flock}",
    response_class=FormattedJSONResponse,
    response_model=FlockData,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    summary="Status of flock",
)
async def get_flock(
    flock: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> FlockData:
    return context.manager.get_flock(flock).dump()


@external_router.put(
    "/flocks/{flock}",
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    status_code=202,
    summary="Signal a flock to refresh",
)
async def refresh_flock(
    flock: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> None:
    context.logger.info("Signaling flock to refresh", flock=flock)
    context.manager.refresh_flock(flock)


@external_router.delete(
    "/flocks/{flock}",
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    status_code=204,
    summary="Stop a flock",
)
async def delete_flock(
    flock: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> None:
    context.logger.info("Deleting flock", flock=flock)
    await context.manager.stop_flock(flock)


@external_router.get(
    "/flocks/{flock}/monkeys",
    response_class=FormattedJSONResponse,
    response_model=list[str],
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    summary="Monkeys in flock",
)
async def get_monkeys(
    flock: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> list[str]:
    return context.manager.get_flock(flock).list_monkeys()


@external_router.get(
    "/flocks/{flock}/monkeys/{monkey}",
    response_class=FormattedJSONResponse,
    response_model=MonkeyData,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    responses={
        404: {"description": "Monkey or flock not found", "model": ErrorModel}
    },
    summary="Status of monkey",
)
async def get_monkey(
    flock: str,
    monkey: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> MonkeyData:
    return context.manager.get_flock(flock).get_monkey(monkey).dump()


@external_router.get(
    "/flocks/{flock}/monkeys/{monkey}/log",
    description="Returns the monkey log output as a file",
    response_class=StreamingResponse,
    responses={
        404: {"description": "Monkey or flock not found", "model": ErrorModel}
    },
    summary="Log for monkey",
)
def get_monkey_log(
    flock: str,
    monkey: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> StreamingResponse:
    logfile = context.manager.get_flock(flock).get_monkey(monkey).logfile()

    # We can't use FileResponse because the log file is constantly changing
    # while it is being streamed back to the client, and Starlette commits to
    # a length but doesn't stop sending the file at that length, resulting in
    # an HTTP protocol error because the content is longer than the declared
    # Content-Length. Instead use a StreamingResponse, but simulate a
    # FileResponse by setting Content-Disposition.
    #
    # Note that this is not async, so this handler must be sync so that
    # FastAPI will run it in a thread pool.
    def iterfile() -> Iterator[bytes]:
        with Path(logfile).open("rb") as fh:
            yield from fh

    filename = f"{flock}-{monkey}-{current_datetime()}"
    return StreamingResponse(
        iterfile(),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@external_router.get(
    "/flocks/{flock}/summary",
    response_class=FormattedJSONResponse,
    response_model=FlockSummary,
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    summary="Summary of statistics for a flock",
)
async def get_flock_summary(
    flock: str,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> FlockSummary:
    return context.manager.get_flock(flock).summary()


@external_router.post(
    "/run",
    response_class=FormattedJSONResponse,
    response_model=SolitaryResult,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    summary="Run monkey business once",
)
async def put_run(
    solitary_config: SolitaryConfig,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> SolitaryResult:
    context.logger.info(
        "Running solitary monkey",
        config=solitary_config.model_dump(exclude_unset=True),
    )
    solitary = context.factory.create_solitary(solitary_config)
    return await solitary.run()


@external_router.get(
    "/summary",
    response_class=FormattedJSONResponse,
    response_model=list[FlockSummary],
    summary="Summary of statistics for all flocks",
)
async def get_summary(
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> list[FlockSummary]:
    return context.manager.summarize_flocks()
