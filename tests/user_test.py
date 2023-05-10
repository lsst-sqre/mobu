"""Tests for the User class."""

from __future__ import annotations

import pytest
import respx
from safir.dependencies.http_client import http_client_dependency

from mobu.models.user import AuthenticatedUser, User

from .support.gafaelfawr import mock_gafaelfawr


@pytest.mark.asyncio
async def test_generate_token(respx_mock: respx.Router) -> None:
    mock_gafaelfawr(respx_mock, "someuser", 1234, 1234)
    config = User(username="someuser", uidnumber=1234)
    scopes = ["exec:notebook"]

    client = await http_client_dependency()
    user = await AuthenticatedUser.create(config, scopes, client)
    assert user.username == "someuser"
    assert user.uidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.token.startswith("gt-")
