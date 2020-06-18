"""Manager for all the monkeys and their business."""

__all__ = [
    "MonkeyBusinessManager",
]

from dataclasses import dataclass, field
from typing import Dict, List

from aiohttp import web
from aiojobs import Scheduler, create_scheduler

from sciencemonkey.monkey import Monkey


@dataclass
class MonkeyBusinessManager:
    _monkeys: Dict[str, Monkey] = field(default_factory=dict)
    _scheduler: Scheduler = None

    async def init(self, app: web.Application) -> None:
        self._scheduler = await create_scheduler()

    async def cleanup(self, app: web.Application) -> None:
        await self._scheduler.close()

    def fetch_monkey(self, username: str) -> Monkey:
        return self._monkeys[username]

    def list_monkeys(self) -> List[str]:
        return list(self._monkeys.keys())

    async def manage_monkey(self, monkey: Monkey) -> None:
        self._monkeys[monkey.user.username] = monkey
        await monkey.start(self._scheduler)

    async def release_monkey(self, username: str) -> None:
        monkey = self._monkeys.get(username, None)
        if monkey is not None:
            await monkey.stop()
            del self._monkeys[username]
