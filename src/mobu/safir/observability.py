"""Observability tooling."""

import time
from collections.abc import Callable, Mapping, MutableMapping
from datetime import timedelta
from functools import wraps
from typing import Any, Self

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.metrics import Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue

MutableAttributes = MutableMapping[str, AttributeValue]
Attributes = Mapping[str, AttributeValue]


class Timer:
    """Records an OTel histogram metric for timing (in ms) sections of code.

    Can be used as a context manager or a function decorator. In either case,
    attributes can be added when the timer is created.

    When used as a context manager, attributes can also be added in the timed
    code by calling the ``add_attributes`` method, which will merge the
    attributes into its argument into any existing attributes.

    When the context manager or decorator exits, a histogram metric will be
    recorded with all of the accumulated attributes.

    Based on `This unmerged PR <https://github.com/open-telemetry/opentelemetry-python/pull/2827>`_
    to the Python OpenTelemetry SDK.
    """

    def __init__(self, histogram: Histogram) -> None:
        """Create an histogram-backed timer with millisecond units.

        Parameters
        ----------
        meter
            An OTel Meter
        name
            A name for the histogram
        description
            A description of the histogram

        """
        self._start: float
        self._attributes: MutableAttributes = {}
        self._histogram = histogram

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object, **kwargs: dict[str, Any]) -> None:
        ms = round(self.elapsed.microseconds / 1000)
        self._histogram.record(ms, self._attributes)

    def time(self, attributes: Attributes | None = None) -> Self:
        if attributes is None:
            attributes = {}
        self._attributes.update(attributes)
        return self

    def add_attributes(self, attributes: Attributes) -> Self:
        self._attributes.update(attributes)
        return self

    @property
    def elapsed(self) -> timedelta:
        return timedelta(seconds=(time.perf_counter() - self._start))

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapped(*args: list[Any], **kwargs: dict[str, Any]) -> Any:
            with self:
                return func(*args, **kwargs)

        return wrapped


class Observer:
    """Provides an OpenTelemetry tracer and meter."""

    def __init__(self, name: str, *, debug: bool = False) -> None:
        """Create and configure the tracer and meter.

        Note that this currently starts a background thread to collect
        metrics.
        """
        name_resource = Resource(attributes={SERVICE_NAME: name})
        self._debug = debug
        self.tracer = self._initialize_tracer(name_resource)
        self.meter = self._initialize_meter(name_resource)

    def _initialize_tracer(self, name: Resource) -> Tracer:
        provider = TracerProvider(resource=name)
        otlp_processor = BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint="localhost:4317",
                insecure=True,
            )
        )
        provider.add_span_processor(otlp_processor)
        if self._debug:
            console_processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(console_processor)
        return provider.get_tracer("safir.tracer")

    def _initialize_meter(self, name: Resource) -> Meter:
        otlp_metric_reader = PeriodicExportingMetricReader(
            exporter=OTLPMetricExporter(
                endpoint="localhost:4317",
                insecure=True,
            ),
            export_interval_millis=5000,
        )
        readers = [otlp_metric_reader]

        if self._debug:
            console_metric_reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=5000,
            )
            readers.append(console_metric_reader)

        provider = MeterProvider(
            resource=name,
            metric_readers=readers,
            # views=[
            #     View(
            #         instrument_type=Histogram,
            #         instrument_name="*",
            #         aggregation=ExponentialBucketHistogramAggregation(),
            #     )
            # ],
        )
        return provider.get_meter("safir.meter")

    def timer_factory(
        self, name: str, description: str
    ) -> Callable[..., Timer]:
        histogram = self.meter.create_histogram(
            name=name, unit="ms", description=description
        )

        def _create_timer() -> Timer:
            return Timer(histogram)

        return _create_timer


class ObserverDependency:
    def __init__(self) -> None:
        self._observer: Observer | None = None

    def initialize(self, name: str, *, debug: bool = False) -> None:
        self._observer = Observer(name, debug=debug)

    @property
    def observer(self) -> Observer:
        if not self._observer:
            raise RuntimeError("ObserverDependency not initialized")
        return self._observer

    def __call__(self) -> Observer:
        return self.observer


observer_dependency = ObserverDependency()
