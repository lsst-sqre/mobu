"""
Events and metrics to ship to FROGMAP.
"""

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from mobu.safir.events.models import EventModel

from .safir.events.event_manager import EventManager


class TapQueryValues(BaseModel):
    """Aggregateable values for a tap query event."""

    duration_ms: float


class TapQueryAttributes(BaseModel):
    """Filterable values for a tap query event."""

    type: Literal["sync", "async"]


class TapQueryEvent(EventModel):
    """A Tap Query Event."""

    attributes: TapQueryAttributes
    values: TapQueryValues


class Events:
    """All events published by this application."""

    def __init__(self, manager: EventManager) -> None:
        self._manager = manager
        self.tap_query: Callable[
            [TapQueryAttributes, TapQueryValues], Awaitable[None]
        ]

    async def initialize(self) -> None:
        self.tap_query = await self._manager.create_event(
            "tap_query", model=TapQueryEvent
        )


class EventsDependency:
    """Provides events for the app to publish."""

    def __init__(self) -> None:
        self._events: Events | None = None

    async def initialize(self, manager: EventManager) -> None:
        self._events = Events(manager)
        await self._events.initialize()

    @property
    def events(self) -> Events:
        if not self._events:
            raise RuntimeError("EventsDependency not initialized")
        return self._events

    def __call__(self) -> Events:
        return self.events


events_dependency = EventsDependency()
