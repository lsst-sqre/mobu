"""Test web UI."""

from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient
from pytest_golden.plugin import GoldenTestFixture

from ..support.constants import TEST_DATA_DIR
from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business

DATA_DIR = TEST_DATA_DIR / "ui_handlers"


async def setup(client: AsyncClient, respx_mock: respx.Router) -> None:
    """Mock Gafaelfawr and create some flocks."""
    mock_gafaelfawr(respx_mock, fake_token="blah")

    config = {
        "name": "test",
        "count": 1,
        "user_spec": {"username_prefix": "testuser"},
        "scopes": ["exec:notebook"],
        "business": {"type": "EmptyLoop"},
    }
    r = await client.put("/mobu/flocks", json=config)
    assert r.status_code == 201
    await wait_for_business(client, username="testuser1", flock="test")

    config = {
        "name": "anothertest",
        "count": 1,
        "user_spec": {"username_prefix": "anothertestuser"},
        "scopes": ["exec:notebook"],
        "business": {"type": "EmptyLoop"},
    }
    r = await client.put("/mobu/flocks", json=config)
    assert r.status_code == 201
    await wait_for_business(
        client, username="anothertestuser1", flock="anothertest"
    )


@pytest.mark.golden_test("../data/ui_handlers/index.yaml")
@pytest.mark.asyncio
async def test_index(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/flocks.yaml")
@pytest.mark.asyncio
async def test_flocks(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/flocks")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/flock.yaml")
@pytest.mark.asyncio
async def test_flock(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/flock/test")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/pause.yaml")
@pytest.mark.asyncio
async def test_pause(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.post("/mobu/ui/flock/test/pause")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/unpause.yaml")
@pytest.mark.asyncio
async def test_unpause(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.post("/mobu/ui/flock/test/unpause")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/config.yaml")
@pytest.mark.asyncio
async def test_config(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/config")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.golden_test("../data/ui_handlers/ci_disabled.yaml")
@pytest.mark.asyncio
async def test_ci_disabled(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/ci")
    assert r.status_code == 200
    assert r.text == golden.out["output"]


@pytest.mark.usefixtures("_enable_github_ci_app")
@pytest.mark.golden_test("../data/ui_handlers/ci_enabled.yaml")
@pytest.mark.asyncio
async def test_ci_enabled(
    client: AsyncClient, respx_mock: respx.Router, golden: GoldenTestFixture
) -> None:
    await setup(client=client, respx_mock=respx_mock)
    r = await client.get("/mobu/ui/ci")
    assert r.status_code == 200
    assert r.text == golden.out["output"]
