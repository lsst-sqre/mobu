"""Provide a global MonkeyBusinessManager used to manage monkeys."""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from aiohttp import ClientSession
from aiojobs import Scheduler

from ..exceptions import FlockNotFoundException
from ..flock import Flock
from ..models.flock import FlockConfig, FlockSummary

__all__ = ["MonkeyBusinessManager", "monkey_business_manager"]


class MonkeyBusinessManager:
    """Manages all of the running monkeys."""

    def __init__(self) -> None:
        self._flocks: Dict[str, Flock] = {}
        self._scheduler: Optional[Scheduler] = None
        self._session: Optional[ClientSession] = None

    async def __call__(self) -> MonkeyBusinessManager:
        return self

    async def init(self) -> None:
        self._scheduler = Scheduler(limit=1000, pending_limit=0)
        self._session = ClientSession()

    async def cleanup(self) -> None:
        awaits = [self.stop_flock(f) for f in self._flocks]
        await asyncio.gather(*awaits)
        if self._scheduler is not None:
            await self._scheduler.close()
            self._scheduler = None
        if self._session:
            await self._session.close()
            self._session = None

    async def start_flock(self, flock_config: FlockConfig) -> Flock:
        if self._scheduler is None or not self._session:
            raise RuntimeError("MonkeyBusinessManager not initialized")
        flock = Flock(flock_config, self._scheduler, self._session)
        if flock.name in self._flocks:
            await self._flocks[flock.name].stop()
        self._flocks[flock.name] = flock
        await flock.start()
        return flock

    def get_flock(self, name: str) -> Flock:
        flock = self._flocks.get(name)
        if flock is None:
            raise FlockNotFoundException(name)
        return flock

    def list_flocks(self) -> List[str]:
        return sorted(self._flocks.keys())

    def summarize_flocks(self) -> List[FlockSummary]:
        return [f.summary() for _, f in sorted(self._flocks.items())]

    async def stop_flock(self, name: str) -> None:
        flock = self._flocks.get(name)
        if flock is None:
            raise FlockNotFoundException(name)
        del self._flocks[name]
        await flock.stop()


monkey_business_manager = MonkeyBusinessManager()
"""Global manager for all running monkeys."""
