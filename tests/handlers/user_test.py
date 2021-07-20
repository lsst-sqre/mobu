"""Test the login monkey."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest

from tests.support.gafaelfawr import mock_gafaelfawr

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, jupyterhub: None, mock_aioresponses: aioresponses
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    r = await client.post(
        "/mobu/user",
        json={
            "name": "test",
            "business": "JupyterLoginLoop",
            "user": {
                "username": "someuser",
                "uidnumber": 1000,
                "scopes": ["exec:notebook"],
            },
        },
    )
    assert r.status_code == 200
    assert r.json() == {"user": "someuser"}

    r = await client.get("/mobu/user/test")
    assert r.status_code == 200
    assert r.json() == {
        "business": {
            "failure_count": 0,
            "name": "JupyterLoginLoop",
            "success_count": ANY,
            "timings": ANY,
        },
        "restart": False,
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "username": "someuser",
        },
    }

    r = await client.get("/mobu/user/test/log")
    assert r.status_code == 200
    assert "text/plain" in r.headers["Content-Type"]
    assert "filename" in r.headers["Content-Disposition"]
    assert "test-" in r.headers["Content-Disposition"]
    assert "Starting up" in r.text

    r = await client.delete("/mobu/user/test")
    assert r.status_code == 204

    r = await client.get("/mobu/user/test")
    assert r.status_code == 404
    r = await client.get("/mobu/user/test/log")
    assert r.status_code == 404
