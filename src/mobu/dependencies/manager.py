"""Provide a global MonkeyBusinessManager used to manage monkeys."""

from __future__ import annotations

from typing import Dict, List, Optional

from aiojobs import Scheduler, create_scheduler

from ..monkey import Monkey

__all__ = ["monkey_business_manager"]


class MonkeyBusinessManager:
    """Manages all of the running monkeys."""

    def __init__(self) -> None:
        self._scheduler: Optional[Scheduler] = None
        self._monkeys: Dict[str, Monkey] = {}

    async def __call__(self) -> MonkeyBusinessManager:
        return self

    async def init(self) -> None:
        self._scheduler = await create_scheduler(limit=1000, pending_limit=0)

    async def cleanup(self) -> None:
        if self._scheduler:
            await self._scheduler.close()
            self._scheduler = None

    def fetch_monkey(self, name: str) -> Monkey:
        return self._monkeys[name]

    def list_monkeys(self) -> List[str]:
        return list(self._monkeys.keys())

    async def manage_monkey(self, monkey: Monkey) -> None:
        if self._scheduler is None:
            raise RuntimeError("MonkeyBusinessManager not initialized")
        await self.release_monkey(monkey.name)
        self._monkeys[monkey.name] = monkey
        await monkey.start(self._scheduler)

    async def release_monkey(self, name: str) -> None:
        monkey = self._monkeys.get(name, None)
        if monkey is not None:
            await monkey.stop()
            del self._monkeys[name]


monkey_business_manager = MonkeyBusinessManager()
"""Global manager for all running monkeys."""
