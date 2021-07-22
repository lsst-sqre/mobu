"""Test the JupyterPythonLoop business logic."""

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
            "business": "JupyterPythonLoop",
            "user": {
                "username": "someuser",
                "uidnumber": 1000,
                "scopes": ["exec:notebook"],
            },
        },
    )
    assert r.status_code == 201
    assert r.json() == {
        "name": "test",
        "business": {
            "failure_count": 0,
            "name": "JupyterPythonLoop",
            "success_count": 0,
            "timings": ANY,
        },
        "restart": False,
        "state": ANY,
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "username": "someuser",
        },
    }

    # Wait until we've finished at least one loop.  Make sure nothing fails.
    finished = False
    while not finished:
        r = await client.get("/mobu/user/test")
        assert r.status_code == 200
        data = r.json()
        assert data["business"]["failure_count"] == 0
        if data["business"]["success_count"] > 0:
            finished = True

    # Get the client log.
    r = await client.get("/mobu/user/test/log")
    assert r.status_code == 200

    # Check that no exceptions were logged.
    assert "Exception thrown" not in r.text

    # Intentionally do not delete the monkey to check whether aiojobs will
    # shut down properly when the server is shut down.
