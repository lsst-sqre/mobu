"""Handlers for the app's external root, ``/mobu/``."""

import json
from datetime import datetime
from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, JSONResponse
from safir.dependencies.logger import logger_dependency
from safir.metadata import get_metadata
from structlog.stdlib import BoundLogger

from ..config import config
from ..dependencies.manager import (
    MonkeyBusinessManager,
    monkey_business_manager,
)
from ..models import Index

__all__ = ["external_router", "get_index", "get_users", "post_user"]

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
    description=(
        "Document the top-level API here. By default it only returns metadata"
        " about the application."
    ),
    response_model=Index,
    response_model_exclude_none=True,
    summary="Application metadata",
)
async def get_index() -> Index:
    """GET ``/mobu/`` (the app's external root).

    Customize this handler to return whatever the top-level resource of your
    application should return. For example, consider listing key API URLs.
    When doing so, also change or customize the response model in
    mobu.models.metadata.

    By convention, the root of the external API includes a field called
    ``metadata`` that provides the same Safir-generated metadata as the
    internal root endpoint.
    """
    metadata = get_metadata(
        package_name="mobu",
        application_name=config.name,
    )
    return Index(metadata=metadata)


@external_router.get("/user", response_model=List[str])
async def get_users(
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> List[str]:
    return manager.list_monkeys()


@external_router.post("/user", response_model=Dict[str, str])
async def post_user(
    request: Request,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
    logger: BoundLogger = Depends(logger_dependency),
) -> Dict[str, str]:
    body = await request.json()
    logger.info(body)
    monkey = await manager.create_monkey(body)
    return {"user": monkey.name}


@external_router.get("/user/{name}", response_class=FormattedJSONResponse)
async def get_user(
    name: str,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> Union[Dict[str, Any], JSONResponse]:
    try:
        monkey = manager.fetch_monkey(name)
        return monkey.dump()
    except KeyError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": [
                    {
                        "loc": ["path", "name"],
                        "msg": f"Monkey for {name} not found",
                        "type": "monkey_not_found",
                    }
                ]
            },
        )


@external_router.delete("/user/{name}", status_code=204)
async def delete_user(
    name: str,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> None:
    await manager.release_monkey(name)


@external_router.get("/user/{name}/log", response_class=FileResponse)
async def get_user_log(
    name: str,
    manager: MonkeyBusinessManager = Depends(monkey_business_manager),
) -> Union[FileResponse, JSONResponse]:
    try:
        monkey = manager.fetch_monkey(name)
    except KeyError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": [
                    {
                        "loc": ["path", "name"],
                        "msg": f"Monkey for {name} not found",
                        "type": "monkey_not_found",
                    }
                ]
            },
        )
    return FileResponse(
        path=monkey.logfile(),
        media_type="text/plain",
        filename=f"{name}-{datetime.now()}",
    )
