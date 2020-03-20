"""Behaviors for sciencemonkey users."""

__all__ = [
    "Idle",
]

import asyncio
from dataclasses import dataclass

import structlog

from sciencemonkey.user import User

logger = structlog.get_logger(__name__)


@dataclass
class Idle:
    user: User

    async def run(self):
        while True:
            logger.info("Hello world")
            await asyncio.sleep(5)
