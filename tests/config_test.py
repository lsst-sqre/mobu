"""Tests for the mobu configuration."""

import pytest
from safir.testing.data import Data

from mobu.config import Config


def test_sentry_environment(
    data: Data, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOBU_SENTRY_ENVIRONMENT", "test-environment")
    config = Config.from_file(data.path("config/base.yaml"))
    assert config.sentry_environment == "test-environment"
