"""Tests for running a solitary monkey."""

from __future__ import annotations

from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient
from rubin.nublado.client import MockJupyter
from safir.testing.slack import MockSlackWebhook

from ..support.gafaelfawr import mock_gafaelfawr


@pytest.mark.asyncio
async def test_run(client: AsyncClient, respx_mock: respx.Router) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.post(
        "/mobu/run",
        json={
            "user": {"username": "bot-mobu-solitary"},
            "scopes": ["exec:notebook"],
            "business": {"type": "EmptyLoop"},
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert result == {"success": True, "log": ANY}
    assert "Starting up..." in result["log"]
    assert "Shutting down..." in result["log"]


@pytest.mark.asyncio
async def test_error(
    client: AsyncClient,
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
    mock_jupyter: MockJupyter,
) -> None:
    mock_gafaelfawr(respx_mock)

    r = await client.post(
        "/mobu/run",
        json={
            "user": {"username": "bot-mobu-solitary"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NubladoPythonLoop",
                "options": {
                    "code": 'raise Exception("some error")',
                    "spawn_settle_time": 0,
                },
            },
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert result == {"success": False, "error": ANY, "log": ANY}
    assert (
        "bot-mobu-solitary: running code 'raise Exception" in result["error"]
    )
    assert "Exception: some error\n" in result["error"]
    assert "Exception: some error" in result["log"]
