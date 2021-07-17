"""A mock Gafaelfawr for tests."""

from __future__ import annotations

import base64
import os
import time
from typing import TYPE_CHECKING
from unittest.mock import ANY

from aioresponses import CallbackResult

from mobu.config import config

if TYPE_CHECKING:
    from typing import Any, Optional

    from aioresponses import aioresponses

__all__ = ["make_gafaelfawr_token", "mock_gafaelfawr"]


def make_gafaelfawr_token() -> str:
    """Create a random Gafaelfawr token."""
    key = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    secret = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    return f"gt-{key}.{secret}"


def mock_gafaelfawr(
    mocked: aioresponses,
    username: Optional[str] = None,
    uid: Optional[int] = None,
) -> None:
    """Mock out the call to Gafaelfawr to create a user token.

    Optionally verifies that the username and UID provided to Gafaelfawr are
    correct.
    """
    admin_token = config.gafaelfawr_token
    assert admin_token.startswith("gt-")

    def handler(url: str, **kwargs: Any) -> CallbackResult:
        assert kwargs["headers"] == {"Authorization": f"bearer {admin_token}"}
        assert kwargs["json"] == {
            "username": ANY,
            "token_type": "user",
            "token_name": ANY,
            "scopes": ["exec:notebook"],
            "expires": ANY,
            "uid": ANY,
        }
        if username:
            assert kwargs["json"]["username"] == username
        if uid:
            assert kwargs["json"]["uid"] == uid
        assert kwargs["json"]["token_name"].startswith("mobu ")
        assert kwargs["json"]["expires"] > time.time()
        response = {"token": make_gafaelfawr_token()}
        return CallbackResult(payload=response, status=200)

    base_url = config.environment_url
    mocked.post(f"{base_url}/auth/api/v1/tokens", callback=handler)
