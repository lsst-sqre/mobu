"""Business logic for mobu."""

__all__ = [
    "Business",
]

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mobu.monkey import Monkey


@dataclass
class Business:
    monkey: "Monkey"

    async def run(self) -> None:
        logger = self.monkey.log

        while True:
            logger.info("Idling...")
            await asyncio.sleep(5)

    def dump(self) -> dict:
        return {"name": "Idle"}
