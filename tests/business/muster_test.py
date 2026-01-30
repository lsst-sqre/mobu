"""Test the Muster business."""

import pytest
from httpx import AsyncClient
from safir.testing.data import Data

from ..support.muster import MockMuster


@pytest.mark.asyncio
async def test_run(
    data: Data, client: AsyncClient, mock_muster: MockMuster
) -> None:
    config = data.read_json("solitary/input/muster")
    r = await client.post("/mobu/run", json=config)
    assert r.status_code == 200
    data.assert_json_matches(r.json(), "solitary/output/muster")
