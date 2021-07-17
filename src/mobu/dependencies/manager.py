"""Provide a global MonkeyBusinessManager used to manage monkeys."""

from ..monkeybusinessmanager import MonkeyBusinessManager

__all__ = ["monkey_business_manager"]

_manager = MonkeyBusinessManager()
"""Global manager for all running monkeys."""


async def monkey_business_manager() -> MonkeyBusinessManager:
    """Return the global MonkeyBusinessManager."""
    return _manager
