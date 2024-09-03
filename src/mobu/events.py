"""Events and metrics to ship to FROGMAP."""

from typing import Literal

from .safir.events.event_manager import EventManager
from .safir.events.models import Payload


class TapQueryPayload(Payload):
    """Values and attributes for a tap query event."""

    type: Literal["async", "sync"]
    duration_ms: float


class Events:
    """All events published by this application."""

    def __init__(self, manager: EventManager) -> None:
        self._manager = manager

        self.tap_query = self._manager.create_event(
            "tap_query", TapQueryPayload
        )


class EventsDependency:
    """Provides events for the app to publish."""

    def __init__(self) -> None:
        self._events: Events | None = None

    async def initialize(self, manager: EventManager) -> None:
        self._events = Events(manager)
        await manager.create_topics()

    @property
    def events(self) -> Events:
        if not self._events:
            raise RuntimeError("EventsDependency not initialized")
        return self._events

    def __call__(self) -> Events:
        return self.events


events_dependency = EventsDependency()
