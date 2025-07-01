"""Tests for the User class."""

from __future__ import annotations

import pytest
import respx
import structlog
from safir.dependencies.http_client import http_client_dependency

from mobu.models.user import Group, User
from mobu.storage.gafaelfawr import GafaelfawrStorage

from ..support.gafaelfawr import mock_gafaelfawr


@pytest.mark.asyncio
async def test_generate_token(respx_mock: respx.Router) -> None:
    mock_gafaelfawr(respx_mock, "bot-mobu-someuser", 1234, 1234)
    config = User(username="bot-mobu-someuser", uidnumber=1234)
    scopes = ["exec:notebook"]

    client = await http_client_dependency()
    logger = structlog.get_logger(__file__)
    gafaelfawr = GafaelfawrStorage(client, logger)

    user = await gafaelfawr.create_service_token(config, scopes)
    assert user.username == "bot-mobu-someuser"
    assert user.uidnumber == 1234
    assert user.gidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.token.startswith("gt-")


@pytest.mark.asyncio
async def test_groups(respx_mock: respx.Router) -> None:
    groups = [Group(name="g_users", id=10000)]
    mock_gafaelfawr(
        respx_mock,
        "bot-mobu-someuser",
        1234,
        1234,
        groups=[Group(name="g_users", id=10000)],
    )
    config = User(
        username="bot-mobu-someuser",
        uidnumber=1234,
        gidnumber=1234,
        groups=groups,
    )
    scopes = ["exec:notebook"]

    client = await http_client_dependency()
    logger = structlog.get_logger(__file__)
    gafaelfawr = GafaelfawrStorage(client, logger)

    user = await gafaelfawr.create_service_token(config, scopes)
    assert user.username == "bot-mobu-someuser"
    assert user.uidnumber == 1234
    assert user.gidnumber == 1234
    assert user.scopes == ["exec:notebook"]
    assert user.groups == groups
    assert user.token.startswith("gt-")
