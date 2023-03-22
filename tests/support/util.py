"""Utility functions for tests."""

from __future__ import annotations

import asyncio
from typing import Any

from httpx import AsyncClient

__all__ = ["wait_for_business"]


async def wait_for_business(
    client: AsyncClient, username: str, *, flock: str = "test"
) -> dict[str, Any]:
    """Wait for one loop of business to complete and return its data."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/{flock}/monkeys/{username}")
        assert r.status_code == 200
        data = r.json()
        if data["business"]["success_count"] > 0:
            break
        if data["business"]["failure_count"] > 0:
            break
    return data


async def wait_for_flock_start(client: AsyncClient, flock: str) -> None:
    """Wait for all the monkeys in a flock to have started."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/{flock}")
        assert r.status_code == 200
        data = r.json()
        good = True
        for monkey in data["monkeys"]:
            if monkey["state"] != "RUNNING":
                good = False
        if good:
            break
