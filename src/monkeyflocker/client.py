"""Client to talk to the mobu endpoint."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import TracebackType
from typing import Literal
from urllib.parse import urljoin

import structlog
import yaml
from httpx import AsyncClient
from structlog import BoundLogger

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
"""Date format to use for logging."""

SESSION_TIMEOUT = 30
"""How long in seconds to wait for each call."""


class MonkeyflockerClient:
    """The mobu client.

    This communicates with a mobu instance to start or stop a flock of mobu
    monkeys or to retrieve their logs.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url
        self._logger = self._initialize_logging()
        self._client = AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=SESSION_TIMEOUT,
        )

    async def __aenter__(self) -> MonkeyflockerClient:
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        await self.aclose()
        return False

    async def aclose(self) -> None:
        """Shut down the embedded ClientSession."""
        await self._client.aclose()

    async def start(self, spec_file: Path) -> None:
        """Start a flock of monkeys from a specification."""
        assert self._client, "Must be used as a context manager"
        with spec_file.open("r") as f:
            spec = yaml.safe_load(f)
        self._logger.info(f"Starting flock {spec['name']}")
        url = urljoin(self._base_url, "/mobu/flocks")
        r = await self._client.put(url, json=spec)
        r.raise_for_status()
        self._logger.info(f"Flock {spec['name']} started")

    async def report(self, name: str, output: Path) -> None:
        """Generate status and output data for all monkeys."""
        assert self._client, "Must be used as a context manager"
        output.mkdir(parents=True, exist_ok=True)

        self._logger.info(f"Getting status of monkeys in flock {name}")
        flock_url = urljoin(self._base_url, f"/mobu/flocks/{name}")
        r = await self._client.get(flock_url)
        r.raise_for_status()
        data = r.json()
        monkeys = data["monkeys"]

        for monkey in monkeys:
            user = monkey["name"]
            self._logger.info(f"Requesting log for {user}")
            log_url = flock_url + f"/monkeys/{user}/log"
            r = await self._client.get(log_url)
            r.raise_for_status()
            (output / f"{user}_log.txt").write_text(r.text)
            with (output / f"{user}_stats.json").open("w") as f:
                json.dump(monkey, f, indent=4, sort_keys=True)

    async def stop(self, name: str) -> None:
        """Stop a flock of monkeys."""
        assert self._client, "Must be used as a context manager"
        url = urljoin(self._base_url, f"/mobu/flocks/{name}")
        r = await self._client.delete(url)
        r.raise_for_status()

    def _initialize_logging(self) -> BoundLogger:
        """Set up the monkeyflocker logger."""
        formatter = logging.Formatter(
            fmt="%(asctime)s %(message)s", datefmt=DATE_FORMAT
        )
        streamHandler = logging.StreamHandler(stream=sys.stdout)
        streamHandler.setFormatter(formatter)
        logger = logging.getLogger("monkeyflocker")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(streamHandler)
        return structlog.wrap_logger(logger)
