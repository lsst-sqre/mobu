"""Tests for the User class."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession

from mobu.models.user import AuthenticatedUser, UserConfig
from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from aioresponses import aioresponses


@pytest.mark.asyncio
async def test_generate_token(mock_aioresponses: aioresponses) -> None:
    mock_gafaelfawr(mock_aioresponses, "someuser", 1234)
    config = UserConfig(
        username="someuser", uidnumber=1234, scopes=["exec:notebook"]
    )
    async with ClientSession() as session:
        user = await AuthenticatedUser.create(config, session)
    assert user.username == "someuser"
    assert user.uidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.token.startswith("gt-")
