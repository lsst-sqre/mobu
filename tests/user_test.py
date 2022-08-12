"""Tests for the User class."""

from __future__ import annotations

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from mobu.models.user import AuthenticatedUser, User
from tests.support.gafaelfawr import mock_gafaelfawr


@pytest.mark.asyncio
async def test_generate_token(mock_aioresponses: aioresponses) -> None:
    mock_gafaelfawr(mock_aioresponses, "someuser", 1234, 1234)
    config = User(username="someuser", uidnumber=1234)
    scopes = ["exec:notebook"]

    async with ClientSession() as session:
        user = await AuthenticatedUser.create(config, scopes, session)
    assert user.username == "someuser"
    assert user.uidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.token.startswith("gt-")
