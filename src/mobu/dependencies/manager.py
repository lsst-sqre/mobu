"""Provide a global MonkeyBusinessManager used to manage monkeys."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aiohttp import ClientSession
from aiojobs import Scheduler, create_scheduler

from ..business.base import Business
from ..business.jupyterjitterloginloop import JupyterJitterLoginLoop
from ..business.jupyterloginloop import JupyterLoginLoop
from ..business.jupyterpythonloop import JupyterPythonLoop
from ..business.notebookrunner import NotebookRunner
from ..business.querymonkey import QueryMonkey
from ..monkey import Monkey
from ..user import User

__all__ = ["MonkeyBusinessManager", "monkey_business_manager"]


class MonkeyBusinessManager:
    """Manages all of the running monkeys."""

    def __init__(self) -> None:
        self._monkeys: Dict[str, Monkey] = {}
        self._scheduler: Optional[Scheduler] = None
        self._session: Optional[ClientSession] = None

    async def __call__(self) -> MonkeyBusinessManager:
        return self

    async def init(self) -> None:
        self._scheduler = await create_scheduler(limit=1000, pending_limit=0)
        self._session = ClientSession()

    async def cleanup(self) -> None:
        if self._scheduler is not None:
            await self._scheduler.close()
            self._scheduler = None
        if self._session:
            await self._session.close()
            self._session = None
        self._monkeys.clear()

    def fetch_monkey(self, name: str) -> Monkey:
        return self._monkeys[name]

    def list_monkeys(self) -> List[str]:
        return list(self._monkeys.keys())

    async def create_monkey(self, body: Dict[str, Any]) -> Monkey:
        if self._scheduler is None or not self._session:
            raise RuntimeError("MonkeyBusinessManager not initialized")

        name = body["name"]
        business = body["business"]
        user_config = body["user"]
        options = body.get("options", {})

        username = user_config["username"]
        uidnumber = user_config["uidnumber"]
        scopes = user_config["scopes"]

        user = await User.create(username, uidnumber, scopes, self._session)

        # Find the right business class and create the monkey.
        monkey = None
        businesses = [
            Business,
            JupyterLoginLoop,
            JupyterJitterLoginLoop,
            JupyterPythonLoop,
            NotebookRunner,
            QueryMonkey,
        ]
        for b in businesses:
            if business == b.__name__:
                monkey = Monkey(name, user, b, options, self._session)

        # If we fell through, we have no matching business class.
        if not monkey:
            raise ValueError(f"Unknown business {business}")

        # Start and manage the monkey.
        await self.release_monkey(monkey.name)
        self._monkeys[monkey.name] = monkey
        await monkey.start(self._scheduler)

        # Return the monkey in case the caller wants to examine it.
        return monkey

    async def release_monkey(self, name: str) -> None:
        monkey = self._monkeys.get(name, None)
        if monkey is not None:
            await monkey.stop()
            del self._monkeys[name]


monkey_business_manager = MonkeyBusinessManager()
"""Global manager for all running monkeys."""
