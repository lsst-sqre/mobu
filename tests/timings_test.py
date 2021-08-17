"""Test the Timings class."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mobu.timings import Timings


def test_timings() -> None:
    timings = Timings()
    assert timings.dump() == []

    now = datetime.now(tz=timezone.utc)
    with timings.start("something") as sw:
        assert sw.event == "something"
        assert sw.annotations == {}
        assert now + timedelta(seconds=5) > sw.start_time >= now
        assert sw.stop_time is None
        assert sw.elapsed <= datetime.now(tz=timezone.utc) - sw.start_time
        old_elapsed = sw.elapsed

    first_sw = sw
    assert first_sw.stop_time
    assert first_sw.stop_time > first_sw.start_time
    assert first_sw.elapsed == first_sw.stop_time - first_sw.start_time
    assert first_sw.elapsed >= old_elapsed

    with pytest.raises(Exception):
        with timings.start("else", {"foo": "bar"}) as sw:
            assert sw.annotations == {"foo": "bar"}
            assert sw.stop_time is None
            raise Exception("some exception")

    second_sw = sw
    assert second_sw.stop_time
    assert second_sw.stop_time > second_sw.start_time
    assert second_sw.elapsed == second_sw.stop_time - second_sw.start_time

    assert timings.dump() == [
        {
            "event": "something",
            "annotations": {},
            "start": first_sw.start_time.isoformat(),
            "stop": first_sw.stop_time.isoformat(),
            "elapsed": first_sw.elapsed.total_seconds(),
        },
        {
            "event": "else",
            "annotations": {"foo": "bar"},
            "start": second_sw.start_time.isoformat(),
            "stop": second_sw.stop_time.isoformat(),
            "elapsed": second_sw.elapsed.total_seconds(),
            "previous": {
                "event": "something",
                "start": first_sw.start_time.isoformat(),
            },
            "elapsed_since_previous_stop": (
                second_sw.start_time - first_sw.stop_time
            ).total_seconds(),
        },
    ]

    with timings.start("incomplete") as sw:
        dump = timings.dump()
        assert dump[2] == {
            "event": "incomplete",
            "annotations": {},
            "start": sw.start_time.isoformat(),
            "stop": None,
            "elapsed": None,
            "previous": {
                "event": "else",
                "start": second_sw.start_time.isoformat(),
            },
            "elapsed_since_previous_stop": (
                sw.start_time - second_sw.stop_time
            ).total_seconds(),
        }
