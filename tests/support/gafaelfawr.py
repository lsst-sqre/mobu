"""A mock Gafaelfawr for tests."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Any
from unittest.mock import ANY

import respx
from httpx import Request, Response
from safir.datetime import current_datetime

from mobu.dependencies.config import config_dependency
from mobu.models.user import Group

__all__ = ["make_gafaelfawr_token", "mock_gafaelfawr"]


def make_gafaelfawr_token(user: str | None = None) -> str:
    """Create a random or user Gafaelfawr token.

    If a user is given, embed the username in the key portion of the token so
    that we can extract it later.  This means the token no longer follows the
    format of a valid Gafaelfawr token, but it lets the mock JupyterHub know
    what user is being authenticated.
    """
    if user:
        key = base64.urlsafe_b64encode(user.encode()).decode()
    else:
        key = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    secret = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    return f"gt-{key}.{secret}"


def mock_gafaelfawr(
    respx_mock: respx.Router,
    username: str | None = None,
    uid: int | None = None,
    gid: int | None = None,
    *,
    any_uid: bool = False,
    scopes: list[str] | None = None,
    groups: list[Group] | None = None,
) -> None:
    """Mock out the call to Gafaelfawr to create a user token.

    Optionally verifies that the username and UID provided to Gafaelfawr are
    correct.
    """
    config = config_dependency.config
    scopes = scopes or ["exec:notebook"]
    admin_token = config.gafaelfawr_token
    groups_json = [g.model_dump(mode="json") for g in groups or []]
    assert admin_token
    assert admin_token.startswith("gt-")

    def handler(request: Request) -> Response:
        assert request.headers["Authorization"] == f"Bearer {admin_token}"
        expected: dict[str, Any] = {
            "username": username if username else ANY,
            "token_type": "service",
            "scopes": scopes,
            "expires": ANY,
            "name": "Mobu Test User",
            "groups": groups_json,
        }
        if uid:
            expected["uid"] = uid
            if gid:
                expected["gid"] = gid
        elif any_uid:
            expected["uid"] = ANY
            expected["gid"] = ANY
        body = json.loads(request.content)
        assert body == expected
        assert datetime.fromisoformat(body["expires"]) > current_datetime()
        response = {"token": make_gafaelfawr_token(body["username"])}
        return Response(200, json=response)

    base_url = str(config.environment_url).rstrip("/")
    respx_mock.post(f"{base_url}/auth/api/v1/tokens").mock(side_effect=handler)
