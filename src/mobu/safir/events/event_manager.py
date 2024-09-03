from __future__ import annotations

import ssl
from datetime import UTC, datetime

from aiokafka.admin.client import AIOKafkaAdminClient, NewTopic
from faststream.kafka import KafkaBroker
from faststream.kafka.publisher.asyncapi import AsyncAPIDefaultPublisher
from faststream.security import SASLScram512

from .models import EventModel, Payload

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


class Event[P: Payload]:
    """A publisher for one specific type of event."""

    def __init__(
        self,
        name: str,
        event_manager: EventManager,
        publisher: AsyncAPIDefaultPublisher,
    ) -> None:
        self._name = name
        self._event_manager = event_manager
        self._publisher = publisher

    async def publish(self, *, payload: P) -> None:
        await self._event_manager.publish(self._name, payload, self._publisher)


class EventManager:
    """Tools for publishing events."""

    def __init__(self) -> None:
        self._service: str
        self._broker: KafkaBroker
        self._admin_client: AIOKafkaAdminClient
        self._publishers: dict[str, AsyncAPIDefaultPublisher] = {}
        self._topics: set[str] = set()
        self._topic_prefix: str

    async def initialize(
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
            sasl_mechanism="SCRAM-SHA-512",
            sasl_plain_username=sasl_username,
            sasl_plain_password=sasl_password,
            ssl_context=ssl_context,
        )

        await self._broker.start()
        await self._admin_client.start()

    def create_event[P: Payload](
        self, name: str, payload_class: type[P]
    ) -> Event[P]:
        payload_class.validate_field_types()

        if name in self._topics:
            raise RuntimeError(
                f"{name}: you have already created an event with this name."
                " Events must have unique names."
            )
        self._topics.add(name)
        publisher = self._broker.publisher(
            f"{self._topic_prefix}.{name}", schema=EventModel[P]
        )

        return Event[P](name, self, publisher)

    async def publish(
        self, name: str, payload: Payload, publisher: AsyncAPIDefaultPublisher
    ) -> None:
        event = EventModel(
            name=name,
            service=self._service,
            timestamp=datetime.now(UTC),
            payload=payload,
        )
        await publisher.publish(event)

    async def create_topics(self) -> None:
        for name in self._topics:
            topic = NewTopic(
                name=f"{self._topic_prefix}.{name}",
                num_partitions=1,
                replication_factor=3,
            )
            await self._admin_client.create_topics([topic])

    async def aclose(self) -> None:
        await self._broker.close()
        await self._admin_client.close()
