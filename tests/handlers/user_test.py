"""Test the login monkey."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest
from aioresponses import aioresponses

from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.jupyterhub import mock_jupyterhub

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_run(client: AsyncClient, admin_token: str) -> None:
    with aioresponses() as mocked:
        mock_gafaelfawr(mocked)
        mock_jupyterhub(mocked, "someuser")
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
