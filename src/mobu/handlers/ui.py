"""Handlers for the web-based User Interface."""

from typing import Annotated, Any

from devtools import pformat
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from mobu.models.github import GitHubConfig
from mobu.services.github_ci.ci_manager import CiManager

from ..config import config
from ..constants import TEMPLATE_DIR
from ..dependencies.context import RequestContext, context_dependency
from ..dependencies.github import (
    maybe_ci_manager_dependency,
    maybe_github_config_dependency,
)

__all__ = ["router"]


def template_context(request: Request) -> dict[str, Any]:
    """Variables and functions available to every template."""
    return {"config": config, "pformat": pformat}


templates = Jinja2Templates(
    directory=TEMPLATE_DIR, context_processors=[template_context]
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def ui_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html.jinja")


@router.get("/flocks", response_class=HTMLResponse)
async def ui_flocks(
    request: Request,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> HTMLResponse:
    flocks = [
        context.manager.get_flock(name=flock).dump()
        for flock in context.manager.list_flocks()
    ]
    return templates.TemplateResponse(
        request=request, name="flocks.html.jinja", context={"flocks": flocks}
    )


@router.get("/ci", response_class=HTMLResponse)
async def ui_ci(
    request: Request,
    ci_manager: Annotated[
        CiManager | None, Depends(maybe_ci_manager_dependency)
    ],
) -> HTMLResponse:
    if ci_manager:
        return templates.TemplateResponse(
            request=request,
            name="ci.html.jinja",
            context={"ci_manager": ci_manager.summarize()},
        )
    else:
        return templates.TemplateResponse(
            request=request,
            name="ci_not_enabled.html.jinja",
        )


@router.get("/flock/{flock_name}", response_class=HTMLResponse)
async def ui_flock(
    flock_name: str,
    request: Request,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> HTMLResponse:
    flock = context.manager.get_flock(name=flock_name).dump(strip_timings=True)
    return templates.TemplateResponse(
        request=request,
        name="flock.html.jinja",
        context={"flock": flock},
    )


@router.post("/flock/{flock_name}/pause", response_class=HTMLResponse)
async def ui_pause_flock(
    flock_name: str,
    request: Request,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> HTMLResponse:
    context.manager.pause_flock(flock_name)
    flock = context.manager.get_flock(name=flock_name).dump(strip_timings=True)
    return templates.TemplateResponse(
        request=request,
        name="responses/_pause.html.jinja",
        context={
            "flock": flock,
            "state": "paused",
        },
    )


@router.post("/flock/{flock_name}/unpause", response_class=HTMLResponse)
async def ui_unpause_flock(
    flock_name: str,
    request: Request,
    context: Annotated[RequestContext, Depends(context_dependency)],
) -> HTMLResponse:
    context.manager.unpause_flock(flock_name)
    flock = context.manager.get_flock(name=flock_name).dump(strip_timings=True)
    return templates.TemplateResponse(
        request=request,
        name="responses/_pause.html.jinja",
        context={
            "flock": flock,
            "state": "unpaused",
        },
    )


@router.get("/config", response_class=HTMLResponse)
async def ui_config(
    request: Request,
    context: Annotated[RequestContext, Depends(context_dependency)],
    github_config: Annotated[
        GitHubConfig, Depends(maybe_github_config_dependency)
    ],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="config.html.jinja",
        context={"github_config": github_config},
    )
