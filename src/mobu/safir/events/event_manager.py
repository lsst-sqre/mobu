from __future__ import annotations

import ssl
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from faststream.kafka import KafkaBroker
from faststream.kafka.publisher.asyncapi import AsyncAPIDefaultPublisher
from faststream.security import SASLScram512
from pydantic import BaseModel

from .models import EventModel

# class Timer[A]:
#     def __init__(self, name: str, metrics: Metrics) -> None:
#         self._name = name
#         self._metrics: Metrics = metrics
#         self._start: float
#         self._attributes: A
#
#     def __enter__(self) -> Self:
#         self._start = time.perf_counter()
#         return self
#
#     def __exit__(self, *args: object, **kwargs: dict[str, Any]) -> None:
#         ms = round(self.elapsed.microseconds / 1000)
#         self._metrics.publish_duration()
#
#     def time(self, attributes: A) -> Self:
#         self._attributes = attributes
#         return self
#
#     @property
#     def elapsed(self) -> timedelta:
#         return timedelta(seconds=(time.perf_counter() - self._start))


class Event:
    """A publisher for one specific type of event."""

    def __init__(self, name: str, event_manager: EventManager) -> None:
        self._name = name
        self._event_manager: EventManager = event_manager

    async def publish(
        self, *, attributes: BaseModel, values: BaseModel
    ) -> None:
        await self._event_manager.publish(
            self._name, attributes=attributes, values=values
        )


class EventManager:
    """Tools for publishing events."""

    def __init__(self) -> None:
        self._service: str
        self._broker: KafkaBroker
        self._admin_client: AIOKafkaAdminClient
        self._publishers: dict[str, AsyncAPIDefaultPublisher] = {}
        self._topic_prefix: str

    def initialize(
        self,
        service: str,
        base_topic_prefix: str,
        bootstrap_servers: str,
        sasl_username: str,
        sasl_password: str,
    ) -> None:
        self._service = service
        self._topic_prefix = f"{base_topic_prefix}.{service}"

        ssl_context = ssl.create_default_context()
        self._broker = KafkaBroker(
            bootstrap_servers=bootstrap_servers,
            client_id=f"safir-metrics-client-{self._service}",
            security=SASLScram512(
                username=sasl_username,
                password=sasl_password,
                ssl_context=ssl_context,
            ),
        )
        self._admin_client = AIOKafkaAdminClient(
            bootstrap_servers=[
                "sasquatch-dev-kafka-bootstrap.lsst.cloud:9094"
            ],
            client_id="dfuchs-test-metrics-admin",
            security_protocol="SASL_SSL",
            sasl_plain_username=sasl_username,
            sasl_plain_password=sasl_password,
            ssl_context=ssl_context,
        )

    async def create_event[A, V](
        self, name: str, model: type[EventModel[A, V]]
    ) -> Callable[[A, V], Awaitable[None]]:
        await self._register_event(name, model)

        async def publish(attributes: A, values: V) -> None:
            event = model(
                name=name,
                service=self._service,
                timestamp=datetime.now(UTC),
                attributes=attributes,
                values=values,
            )
            publisher = self._publishers[name]
            await publisher.publish(event)

        return publish

    async def publish(
        self, name: str, attributes: BaseModel, values: BaseModel
    ) -> None:
        event = EventModel(
            name=name,
            service=self._service,
            timestamp=datetime.now(UTC),
            attributes=attributes,
            values=values,
        )
        publisher = self._publishers[name]
        await publisher.publish(event)

    async def _register_event[A, V](
        self, name: str, model: type[EventModel[A, V]]
    ) -> None:
        topic = NewTopic(
            name=f"{self._topic_prefix}.{name}",
            num_partitions=1,
            replication_factor=3,
        )
        await self._admin_client.create_topics([topic])
        self._publishers[name] = self._broker.publisher(name, schema=model)
