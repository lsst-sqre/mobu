"""Manager for all the monkeys and their business."""

__all__ = [
    "MonkeyBusinessManager",
]

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aiohttp import web
from aiojobs import Scheduler, create_scheduler
from aiojobs._job import Job

from sciencemonkey.business import Business


@dataclass
class MonkeyBusinessManager:
    _monkeys: Dict[str, Tuple[Business, Job]] = field(default_factory=dict)
    _scheduler: Scheduler = None

    async def init(self, app: web.Application) -> None:
        self._scheduler = await create_scheduler()

    async def cleanup(self, app: web.Application) -> None:
        await self._scheduler.close()

    def fetch_monkey(self, username: str) -> Business:
        return self._monkeys[username]

    def list_monkeys(self) -> List[str]:
        return list(self._monkeys.keys())

    async def manage_monkey(self, monkey: Business) -> None:
        job = await self._scheduler.spawn(monkey.run())
        self._monkeys[monkey.user.username] = (monkey, job)

    async def release_monkey(self, username: str) -> None:
        monkey = self._monkeys.get(username, None)
        if monkey is not None:
            await monkey[1].close()
            del self._monkeys[username]
