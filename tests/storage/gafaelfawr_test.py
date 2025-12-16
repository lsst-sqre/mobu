"""Tests for the User class."""

from __future__ import annotations

import pytest
import structlog
from rubin.gafaelfawr import (
    GafaelfawrClient,
    GafaelfawrGroup,
    GafaelfawrUserInfo,
)

from mobu.dependencies.config import config_dependency
from mobu.models.user import Group, User
from mobu.storage.gafaelfawr import GafaelfawrStorage


@pytest.mark.asyncio
async def test_generate_token() -> None:
    config = config_dependency.config
    user = User(username="bot-mobu-someuser", uidnumber=1234)
    scopes = ["exec:notebook"]

    client = GafaelfawrClient()
    logger = structlog.get_logger(__file__)
    gafaelfawr = GafaelfawrStorage(config, client, logger)

    auth_user = await gafaelfawr.create_service_token(user, scopes)
    assert auth_user.username == "bot-mobu-someuser"
    assert auth_user.uidnumber == 1234
    assert auth_user.gidnumber == 1234
    assert auth_user.scopes == ["exec:notebook"]
    assert auth_user.token.startswith("gt-")

    userinfo = await client.get_user_info(auth_user.token)
    assert userinfo == GafaelfawrUserInfo(
        username="bot-mobu-someuser", name="Mobu Test User", uid=1234, gid=1234
    )


@pytest.mark.asyncio
async def test_groups() -> None:
    config = config_dependency.config
    groups = [Group(name="g_users", id=10000)]
    user = User(
        username="bot-mobu-someuser",
        uidnumber=1234,
        gidnumber=1234,
        groups=groups,
    )
    scopes = ["exec:notebook"]

    client = GafaelfawrClient()
    logger = structlog.get_logger(__file__)
    gafaelfawr = GafaelfawrStorage(config, client, logger)

    auth_user = await gafaelfawr.create_service_token(user, scopes)
    assert auth_user.username == "bot-mobu-someuser"
    assert auth_user.uidnumber == 1234
    assert auth_user.gidnumber == 1234
    assert auth_user.scopes == ["exec:notebook"]
    assert auth_user.groups == groups
    assert auth_user.token.startswith("gt-")

    userinfo = await client.get_user_info(auth_user.token)
    assert userinfo == GafaelfawrUserInfo(
        username="bot-mobu-someuser",
        name="Mobu Test User",
        uid=1234,
        gid=1234,
        groups=[GafaelfawrGroup(name="g_users", id=10000)],
    )
