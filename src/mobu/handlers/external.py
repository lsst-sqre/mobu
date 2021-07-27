"""Handlers for the app's external root, ``/mobu/``."""

import json
from datetime import datetime
from typing import Any, List
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse, JSONResponse
from safir.dependencies.logger import logger_dependency
from safir.metadata import get_metadata
from structlog.stdlib import BoundLogger

from ..config import config
from ..dependencies.manager import (
    MonkeyBusinessManager,
    monkey_business_manager,
)
from ..models.error import ErrorModel
from ..models.flock import FlockConfig, FlockData
from ..models.index import Index
from ..models.monkey import MonkeyData

__all__ = [
    "external_router",
    "delete_flock",
    "get_flock",
    "get_flocks",
    "get_index",
    "get_monkey",
    "get_monkeys",
    "get_monkey_log",
    "put_flock",
]

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
    """GET ``/mobu/`` (the app's external root).

    Customize this handler to return whatever the top-level resource of your
    application should return. For example, consider listing key API URLs.
    When doing so, also change or customize the response model in
    mobu.models.index.

    By convention, the root of the external API includes a field called
    ``metadata`` that provides the same Safir-generated metadata as the
    internal root endpoint.
    """
    metadata = get_metadata(
        package_name="mobu",
        application_name=config.name,
    )
    return Index(metadata=metadata)


@external_router.get(
    "/flocks", response_model=List[str], summary="List running flocks"
)
async def get_flocks(
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> List[str]:
    return manager.list_flocks()


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
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
    logger: BoundLogger = Depends(logger_dependency),
) -> FlockData:
    logger.info("Creating flock: %s", flock_config.dict())
    flock = await manager.start_flock(flock_config)
    response.headers["Location"] = quote(f"/mobu/flocks/{flock.name}")
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
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> FlockData:
    return manager.get_flock(flock).dump()


@external_router.delete(
    "/flocks/{flock}",
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    status_code=204,
    summary="Stop a flock",
)
async def delete_flock(
    flock: str,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> None:
    await manager.stop_flock(flock)


@external_router.get(
    "/flocks/{flock}/monkeys",
    response_class=FormattedJSONResponse,
    response_model=List[str],
    responses={404: {"description": "Flock not found", "model": ErrorModel}},
    summary="Monkeys in flock",
)
async def get_monkeys(
    flock: str,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> List[str]:
    return manager.get_flock(flock).list_monkeys()


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
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> MonkeyData:
    return manager.get_flock(flock).get_monkey(monkey).dump()


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
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> FileResponse:
    return FileResponse(
        path=manager.get_flock(flock).get_monkey(monkey).logfile(),
        media_type="text/plain",
        filename=f"{flock}-{monkey}-{datetime.now()}",
    )
