"""Handlers for the app's external root, ``/mobu/``."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse, JSONResponse
from safir.datetime import current_datetime
from safir.metadata import get_metadata
from safir.models import ErrorModel

from ..config import config
from ..dependencies.context import RequestContext, context_dependency
from ..models.flock import FlockConfig, FlockData, FlockSummary
from ..models.index import Index
from ..models.monkey import MonkeyData

external_router = APIRouter()
"""FastAPI router for all external handlers."""


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
    context: RequestContext = Depends(context_dependency),
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
    context: RequestContext = Depends(context_dependency),
) -> FlockData:
    context.logger.info(
        "Creating flock",
        flock=flock_config.name,
        config=flock_config.dict(exclude_unset=True),
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
    context: RequestContext = Depends(context_dependency),
) -> FlockData:
    return context.manager.get_flock(flock).dump()


@external_router.delete(
    "/flocks/{flock}",
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    status_code=204,
    summary="Stop a flock",
)
async def delete_flock(
    flock: str,
    context: RequestContext = Depends(context_dependency),
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
    context: RequestContext = Depends(context_dependency),
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
    context: RequestContext = Depends(context_dependency),
) -> MonkeyData:
    return context.manager.get_flock(flock).get_monkey(monkey).dump()


@external_router.get(
    "/flocks/{flock}/monkeys/{monkey}/log",
    description="Returns the monkey log output as a file",
    response_class=FileResponse,
    responses={
        404: {"description": "Monkey or flock not found", "model": ErrorModel}
    },
    summary="Log for monkey",
)
async def get_monkey_log(
    flock: str,
    monkey: str,
    context: RequestContext = Depends(context_dependency),
) -> FileResponse:
    return FileResponse(
        path=context.manager.get_flock(flock).get_monkey(monkey).logfile(),
        media_type="text/plain",
        filename=f"{flock}-{monkey}-{current_datetime()}",
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
    context: RequestContext = Depends(context_dependency),
) -> FlockSummary:
    return context.manager.get_flock(flock).summary()


@external_router.get(
    "/summary",
    response_class=FormattedJSONResponse,
    response_model=list[FlockSummary],
    summary="Summary of statistics for all flocks",
)
async def get_summary(
    context: RequestContext = Depends(context_dependency),
) -> list[FlockSummary]:
    return context.manager.summarize_flocks()
