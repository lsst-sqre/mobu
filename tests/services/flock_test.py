"""Tests for flock functionality."""

from time import perf_counter

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_batched_start(client: AsyncClient) -> None:
    # Set up our mocked business. This will wait for all batches to have
    # attempted to start.
    start = perf_counter()
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 10,
            "start_batch_size": 3,
            "start_batch_wait": "1s",
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "EmptyLoop",
            },
        },
    )
    end = perf_counter()

    assert r.status_code == 201

    # Make sure it took at least as much time as the total of the waits
    elapsed = end - start
    assert elapsed > 3
