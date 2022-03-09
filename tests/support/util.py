"""Utility functions for tests."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from httpx import AsyncClient

__all__ = ["wait_for_business"]


async def wait_for_business(
    client: AsyncClient, username: str
) -> Dict[str, Any]:
    """Wait for one loop of business to complete and return its data."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/test/monkeys/{username}")
        assert r.status_code == 200
        data = r.json()
        if data["business"]["success_count"] > 0:
            break
        if data["business"]["failure_count"] > 0:
            break
    return data
