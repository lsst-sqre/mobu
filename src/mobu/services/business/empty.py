"""EmptyLoop business logic for mobu."""

from __future__ import annotations

from .base import Business

__all__ = ["EmptyLoop"]


class EmptyLoop(Business):
    """Business class that does nothing, successfully.

    This is a minimal business class that does nothing. It is primarily used
    for testing mobu.
    """

    async def execute(self) -> None:
        pass
