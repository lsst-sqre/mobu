"""Mock JupyterLab Controller for tests."""

from __future__ import annotations

import json
from typing import Any

from aioresponses import CallbackResult, aioresponses

from mobu.config import config

__all__ = ["MockController", "mock_controller"]


class MockController:
    """Mock of JupyterLab Controller that implements only the available images
    API."""

    def __init__(self) -> None:
        self.images = {
            "recommended": {
                "path": "docker.io/lsstsqre/sciplat-lab:recommended",
                "tags": {"recommended": "Recommended (Weekly 2023_03)"},
                "name": "Recommended (Weekly 2023_03)",
                "prepulled": True,
            },
            "latest-weekly": {
                "path": "docker.io/lsstsqre/sciplat-lab:w_2023_05",
                "tags": {"w_2023_05": "Weekly 2023_05"},
                "name": "Weekly 2023_05",
                "prepulled": True,
            },
            "latest-daily": {
                "path": "docker.io/lsstsqre/sciplat-lab:d_2023_02_02",
                "tags": {"d_2023_02_02": "Daily 2023_02_02"},
                "name": "Daily 2023_02_02",
                "prepulled": True,
            },
            "latest-release": {
                "path": "docker.io/lsstsqre/sciplat-lab:r24_0_0",
                "tags": {"r24_0_0": "Release r24.0.0"},
                "name": "Release r24.0.0",
                "prepulled": True,
            },
            "all": [
                {
                    "path": "docker.io/lsstsqre/sciplat-lab:recommended",
                    "tags": {"recommended": "Recommended (Weekly 2023_03)"},
                    "name": "Recommended (Weekly 2023_03)",
                    "prepulled": True,
                },
                {
                    "path": "docker.io/lsstsqre/sciplat-lab:w_2023_05",
                    "tags": {"w_2023_05": "Weekly 2023_05"},
                    "name": "Weekly 2023_05",
                    "prepulled": True,
                },
                {
                    "path": "docker.io/lsstsqre/sciplat-lab:d_2023_02_02",
                    "tags": {"d_2023_02_02": "Daily 2023_02_02"},
                    "name": "Daily 2023_02_02",
                    "prepulled": True,
                },
                {
                    "path": "docker.io/lsstsqre/sciplat-lab:r24_0_0",
                    "tags": {"r24_0_0": "Release r24.0.0"},
                    "name": "Release r24.0.0",
                    "prepulled": True,
                },
            ],
        }

    def available(self, url: str, **kwargs: Any) -> CallbackResult:
        body = self.images
        return CallbackResult(status=200, body=json.dumps(body))


def mock_controller(mocked: aioresponses) -> MockController:
    """Set up a mock JupyterLab Controller."""
    mock = MockController()
    url = f"{config.environment_url}/nublado/spawner/v1/images"
    mocked.get(url, callback=mock.available, repeat=True)
    return mock
