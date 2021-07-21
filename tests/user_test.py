"""Tests for the User class."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession

from mobu.user import User
from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from aioresponses import aioresponses


@pytest.mark.asyncio
async def test_generate_token(mock_aioresponses: aioresponses) -> None:
    mock_gafaelfawr(mock_aioresponses, "someuser", 1234)
    async with ClientSession() as session:
        user = await User.create("someuser", 1234, ["exec:notebook"], session)
    assert user.username == "someuser"
    assert user.uidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.token.startswith("gt-")
