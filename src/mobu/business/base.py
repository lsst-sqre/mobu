"""Business logic for mobu."""

__all__ = [
    "Business",
]

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from mobu.monkey import Monkey


@dataclass
class Business:
    monkey: "Monkey"
    options: Dict[str, Any]

    async def run(self) -> None:
        logger = self.monkey.log

        while True:
            logger.info("Idling...")
            await asyncio.sleep(5)

    async def stop(self) -> None:
        pass

    def dump(self) -> dict:
        return {"name": "Idle"}
