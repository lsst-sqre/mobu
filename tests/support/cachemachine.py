"""Mock cachemachine for tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aioresponses import CallbackResult

from mobu.config import config

if TYPE_CHECKING:
    from typing import Any

    from aioresponses import aioresponses

__all__ = ["MockCachemachine", "mock_cachemachine"]


class MockCachemachine:
    """Mock of cachemachine that implements only the available image API."""

    def __init__(self) -> None:
        self.images = [
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:recommended"
                ),
                "image_hash": (
                    "sha256:c2c67ee6275b861fdf69dfbb42322925118e2b997bfe294519"
                    "01900ba00bba69"
                ),
                "name": "Recommended (Weekly 2021_33)",
            },
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:r22_0_1"
                ),
                "image_hash": (
                    "sha256:72cff1efc7ef6c31cd4afed489d58fec91bdfa4711918b240b"
                    "548c9370914464"
                ),
                "name": "Release r22.0.1",
            },
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_35"
                ),
                "image_hash": (
                    "sha256:ef93e4560a2e06d39300802686392000237f186a9197e8dea2"
                    "4a1dd9abbd6e2c"
                ),
                "name": "Weekly 2021_35",
            },
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:w_2021_34"
                ),
                "image_hash": (
                    "sha256:513c08d9fd0fae9fdd6880bba2781d14c480eec86e7c937856"
                    "cfac1cd1a3baac"
                ),
                "name": "Weekly 2021_34",
            },
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:d_2021_08_31"
                ),
                "image_hash": (
                    "sha256:d99b6067e489657cda0835a34466756ef04e36b597587c3442"
                    "d405457423ee9b"
                ),
                "name": "Daily 2021_08_31",
            },
            {
                "image_url": (
                    "registry.hub.docker.com/lsstsqre/sciplat-lab:d_2021_08_30"
                ),
                "image_hash": (
                    "sha256:16fc46c35b453a2be5593e473d6b102442faaeec42ffda3394"
                    "0f0669d2ac1f88"
                ),
                "name": "Daily 2021_08_30",
            },
        ]

    def available(self, url: str, **kwargs: Any) -> CallbackResult:
        body = {"images": self.images}
        return CallbackResult(status=200, body=json.dumps(body))


def mock_cachemachine(mocked: aioresponses) -> MockCachemachine:
    """Set up a mock cachemachine."""
    mock = MockCachemachine()
    url = f"{config.environment_url}/cachemachine/jupyter/available"
    mocked.get(url, callback=mock.available, repeat=True)
    return mock
