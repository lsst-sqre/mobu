"""Tests for the User class."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses

from mobu.config import Configuration
from mobu.user import User
from tests.support.gafaelfawr import mock_gafaelfawr


@pytest.mark.asyncio
async def test_generate_token(admin_token: str) -> None:
    with aioresponses() as mocked:
        mock_gafaelfawr(mocked, "someuser", 1234)
        user = await User.create("someuser", 1234, ["exec:notebook"])
        assert user.username == "someuser"
        assert user.uidnumber == 1234
        assert user.scopes == ["exec:notebook"]
        assert user.token.startswith("gt-")

    Configuration.gafaelfawr_token = "None"
