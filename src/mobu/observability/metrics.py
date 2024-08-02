from opentelemetry.metrics import CallbackT

from ..safir.observability import Observer


class Metrics:
    """All metrics recorded by the application."""

    def __init__(self, observer: Observer) -> None:
        self.meter = observer.meter

        # Service-specific metrics
        self.service_success = observer.meter.create_counter(
            "service_success",
            description=(
                "Counts successful operations against a phalanx service, like"
                " tap. When recording this metric, put the service name in the"
                " ``service`` attribute."
            ),
        )

        self.service_failure = observer.meter.create_counter(
            "service_failure",
            description=(
                "Counts failed operations against a phalanx service, like"
                " tap. When recording this metric, put the service name in the"
                " ``service`` attribute."
            ),
        )

        # TAP metrics
        self.tap_query_timer = observer.timer_factory(
            "tap_query", description="Time to execute a TAP query"
        )

        self.tap_make_client_timer = observer.timer_factory(
            "tap_make_client", description="Time to create a TAP client"
        )

        # Nublado metrics
        self.nublado_login_timer = observer.timer_factory(
            "nublado_hub_login",
            description="Time to login to the Nublado hub",
        )

        self.nublado_spawn_lab_timer = observer.timer_factory(
            "nublado_spawn_lab",
            description="Time to spawn a nublado lab",
        )

        self.nublado_lab_login_timer = observer.timer_factory(
            "nublado_lab_login",
            description="Time to login to a nublado lab",
        )

        self.nublado_create_session_timer = observer.timer_factory(
            "nublado_create_session",
            description="Time create a nublado session",
        )

        self.nublado_delete_session_timer = observer.timer_factory(
            "nublado_delete_session",
            description="Time delete a nublado session",
        )

    def start_health_gauge(self, callback: CallbackT) -> None:
        self.meter.create_observable_gauge(
            name="business_health",
            description="1 if the business is healthy, 0 if not",
            callbacks=[callback],
        )


class MetricsDependency:
    def __init__(self) -> None:
        self._metrics: Metrics | None = None

    def initialize(self, observer: Observer) -> None:
        self._metrics = Metrics(observer)

    @property
    def metrics(self) -> Metrics:
        if not self._metrics:
            raise RuntimeError("MetricsDependency not initialized")
        return self._metrics

    def __call__(self) -> Metrics:
        return self.metrics


metrics_dependency = MetricsDependency()
