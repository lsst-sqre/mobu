"""Create a version of the app for monkeyflocker testing."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import override

import respx
from fastapi import FastAPI, Request, Response
from rubin.gafaelfawr import register_mock_gafaelfawr
from rubin.nublado.client import register_mock_jupyter
from rubin.repertoire import register_mock_discovery
from starlette.middleware.base import BaseHTTPMiddleware

from mobu.dependencies.config import config_dependency
from mobu.main import create_app as main_create_app

__all__ = ["AddAuthHeaderMiddleware", "create_app"]


class AddAuthHeaderMiddleware(BaseHTTPMiddleware):
    """Mock running behind a Gafaelfawr-aware ingress.

    Pretend Gafaelfawr is doing authentication in front of mobu. This is a
    total hack based on https://github.com/tiangolo/fastapi/issues/2727 that
    adds the header that would have been added by Gafaelfawr. Unfortunately,
    there's no documented way to modify request headers in middleware, so we
    have to muck about with internals.
    """

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.headers.__dict__["_list"].append(
            (b"x-auth-request-user", b"someuser")
        )
        return await call_next(request)


async def _startup() -> None:
    """Additional startup actions to take."""
    respx.start()
    os.environ["REPERTOIRE_BASE_URL"] = "https://example.com/repertoire"
    path = Path(__file__).parent.parent / "data" / "discovery.json"
    register_mock_discovery(respx.mock, path)
    mock_gafaelfawr = await register_mock_gafaelfawr(respx.mock)
    token = mock_gafaelfawr.create_token("bot-mobu", scopes=["admin:token"])
    os.environ["MOBU_GAFAELFAWR_TOKEN"] = token
    config_dependency.config.gafaelfawr_token = token
    await register_mock_jupyter(respx.mock).__aenter__()


def create_app() -> FastAPI:
    """Configure the FastAPI app for monkeyflocker testing.

    This cannot have any arguments. It is run in an isolated process, and
    therefore doesn't need to clean up after its mocking.
    """
    app = main_create_app(startup=_startup())
    app.add_middleware(AddAuthHeaderMiddleware)
    return app
