"""Manager for all the monkeys and their business."""

__all__ = [
    "MonkeyBusinessManager",
]

from dataclasses import dataclass, field
from typing import Dict, List

from aiohttp import web
from aiojobs import Scheduler, create_scheduler

from mobu.monkey import Monkey


@dataclass
class MonkeyBusinessManager:
    _monkeys: Dict[str, Monkey] = field(default_factory=dict)
    _scheduler: Scheduler = None

    async def init(self, app: web.Application) -> None:
        self._scheduler = await create_scheduler()

    async def cleanup(self, app: web.Application) -> None:
        await self._scheduler.close()

    def fetch_monkey(self, name: str) -> Monkey:
        return self._monkeys[name]

    def list_monkeys(self) -> List[str]:
        return list(self._monkeys.keys())

    async def manage_monkey(self, monkey: Monkey) -> None:
        await self.release_monkey(monkey.name)
        self._monkeys[monkey.name] = monkey
        await monkey.start(self._scheduler)

    async def release_monkey(self, name: str) -> None:
        monkey = self._monkeys.get(name, None)
        if monkey is not None:
            await monkey.stop()
            del self._monkeys[name]
