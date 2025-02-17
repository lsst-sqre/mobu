"""EmptyLoop business logic for mobu."""

from __future__ import annotations

from typing import override

from mobu.events import EmptyLoopExecution

from .base import Business

__all__ = ["EmptyLoop"]


class EmptyLoop(Business):
    """Business class that does nothing, successfully.

    This is a minimal business class that does nothing. It is primarily used
    for testing mobu.
    """

    @override
    async def execute(self) -> None:
        await self.events.empty_loop.publish(
            EmptyLoopExecution(success=True, **self.common_event_attrs())
        )
