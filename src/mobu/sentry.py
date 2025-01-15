"""Helpers for sentry instrumentation."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal

import sentry_sdk
from safir.sentry import before_send_handler
from sentry_sdk.tracing import Span, Transaction
from sentry_sdk.types import Event, Hint

from mobu.constants import SENTRY_ERRORED_KEY

__all__ = [
    "before_send",
    "capturing_start_span",
    "fingerprint",
    "start_transaction",
]


def fingerprint(event: Event) -> list[str]:
    """Generate a fingerprint to force separate issues for tag combos."""
    fingerprint = event.get("fingerprint", [])
    return [
        *fingerprint,
        "{{ tags.flock }}",
        "{{ tags.business }}",
        "{{ tags.notebook }}",
        "{{ tags.cell }}",
    ]


def before_send(event: Event, hint: Hint) -> Event | None:
    """Add tags to fingerprint so that distinct issues are created."""
    event["fingerprint"] = fingerprint(event)
    return before_send_handler(event, hint)


@contextmanager
def capturing_start_span(op: str, **kwargs: Any) -> Generator[Span]:
    """Start a span, set the op/start time in the context, and capture errors.

    Setting the op and start time in the context will propagate it to any error
    events that get sent to Sentry, event if the trace does not get sent.

    Explicitly capturing errors in the span will tie the Sentry events to this
    specific span, rather than tying them to the span/transaction where they
    would be handled otherwise.
    """
    with sentry_sdk.start_span(op=op, **kwargs) as span:
        sentry_sdk.get_isolation_scope().set_context(
            "phase", {"phase": op, "started_at": span.start_timestamp}
        )
        sentry_sdk.get_isolation_scope().set_tag("phase", op)

        # You can't see the time a span started in the Sentry UI, only the time
        # the entire transaction started
        span.set_tag("started_at", span.start_timestamp)

        try:
            yield span
        except Exception as e:
            # Even though we're capturing exceptions at the business level,
            # Sentry knows not to send them twice.
            sentry_sdk.capture_exception(e)
            raise
        finally:
            sentry_sdk.get_isolation_scope().remove_context("phase")
            sentry_sdk.get_isolation_scope().remove_tag("phase")


@contextmanager
def start_transaction(
    name: str, op: str, **kwargs: Any
) -> Generator[Transaction | Span]:
    """Start a transaction and mark it if an exception is raised."""
    with sentry_sdk.start_transaction(
        name=name, op=op, **kwargs
    ) as transaction:
        try:
            yield transaction
        except Exception:
            transaction.set_tag(SENTRY_ERRORED_KEY, True)
            raise


@contextmanager
def capturing_isolation_scope() -> Generator:
    """Run in a new isolation scope and capture any uncaught errors."""
    with sentry_sdk.isolation_scope():
        try:
            yield
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            raise


def send_all_error_transactions(event: Event, _: Hint) -> Event | None:
    """Send the transaction if an exception was raised during it."""
    if event.get("tags", {}).get(SENTRY_ERRORED_KEY, False):
        return event
    return None


def sentry_init(
    dsn: str | None, env: str, traces_sample_config: float | Literal["errors"]
) -> None:
    """Initialize Sentry with different functionality based on env vars."""
    if traces_sample_config == "errors":
        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            before_send=before_send,
            traces_sample_rate=1,
            before_send_transaction=send_all_error_transactions,
        )
    else:
        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            before_send=before_send,
            traces_sample_rate=traces_sample_config,
        )
