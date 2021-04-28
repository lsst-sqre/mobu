"""Tests for the User class."""

from __future__ import annotations

import base64
import os
import time
from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest
from aioresponses import CallbackResult, aioresponses

from mobu.config import Configuration
from mobu.user import User

if TYPE_CHECKING:
    from typing import Any, Callable


def make_gafaelfawr_token() -> str:
    key = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    secret = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    return f"gt-{key}.{secret}"


def build_handler(admin_token: str) -> Callable[..., CallbackResult]:
    def handler(url: str, **kwargs: Any) -> CallbackResult:
        assert kwargs["headers"] == {"Authorization": f"bearer {admin_token}"}
        assert kwargs["json"] == {
            "username": "someuser",
            "token_type": "user",
            "token_name": ANY,
            "scopes": ["exec:notebook"],
            "expires": ANY,
            "uid": 1234,
        }
        assert kwargs["json"]["token_name"].startswith("mobu ")
        assert kwargs["json"]["expires"] > time.time()
        response = {"token": make_gafaelfawr_token()}
        return CallbackResult(payload=response, status=200)

    return handler


@pytest.mark.asyncio
async def test_generate_token() -> None:
    admin_token = make_gafaelfawr_token()
    handler = build_handler(admin_token)

    Configuration.gafaelfawr_token = admin_token
    with aioresponses() as m:
        m.post(
            "https://nublado.lsst.codes/auth/api/v1/tokens", callback=handler
        )
        user = await User.create("someuser", 1234, ["exec:notebook"])
        assert user.username == "someuser"
        assert user.uidnumber == 1234
        assert user.scopes == ["exec:notebook"]
        assert user.token.startswith("gt-")
    Configuration.gafaelfawr_token = "None"
