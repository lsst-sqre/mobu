"""Configuration definition."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from safir.logging import LogLevel, Profile

from .safir.metrics.config import Configuration as MetricsConfiguration

__all__ = [
    "Configuration",
    "config",
]


class Configuration(BaseSettings):
    """Configuration for mobu."""

    alert_hook: HttpUrl | None = Field(
        None,
        title="Slack webhook URL used for sending alerts",
        description=(
            "An https URL, which should be considered secret. If not set or"
            " set to `None`, this feature will be disabled."
        ),
        examples=["https://slack.example.com/ADFAW1452DAF41/"],
    )

    autostart: Path | None = Field(
        None,
        title="Path to YAML file defining flocks to automatically start",
        description=(
            "If given, the YAML file must contain a list of flock"
            " specifications. All flocks given there will be automatically"
            " started when mobu starts."
        ),
        validation_alias="MOBU_AUTOSTART_PATH",
        examples=["/etc/mobu/autostart.yaml"],
    )

    github_ci_app_config_path: Path | None = Field(
        None,
        title="GitHub CI app config path",
        description=(
            "Path to YAML file defining settings for GitHub CI app"
            " integration"
        ),
        examples=["/etc/mobu/github-ci-app.yaml"],
    )

    github_refresh_app_config_path: Path | None = Field(
        None,
        title="GitHub refresh app config path",
        description=(
            "Path to YAML file defining settings for GitHub refresh app"
            " integration"
        ),
        examples=["/etc/mobu/github-refresh-app.yaml"],
    )

    environment_url: HttpUrl | None = Field(
        None,
        title="Base URL of the Science Platform environment",
        description=(
            "Used to create URLs to other services, such as Gafaelfawr and"
            " JupyterHub. This is only optional to make writing the test"
            " suite easier. If it is not set to a valid URL, mobu will abort"
            " during startup."
        ),
        examples=["https://data.example.org/"],
    )

    gafaelfawr_token: str | None = Field(
        None,
        title="Gafaelfawr admin token",
        description=(
            "This token is used to make an admin API call to Gafaelfawr to"
            " get a token for the user. This is only optional to make writing"
            " tests easier. mobu will abort during startup if it is not set."
        ),
        examples=["gt-vilSCi1ifK_MyuaQgMD2dQ.d6SIJhowv5Hs3GvujOyUig"],
    )

    available_services: set[str] = Field(
        set(),
        title="Available platform services",
        description=(
            "Names of services available in the current environment. For now,"
            " this list is manually maintained in the mobu config in Phalanx."
            " When we have a service discovery mechanism in place, it should"
            " be used here."
        ),
        examples=[{"tap", "ssotap", "butler"}],
    )

    name: str = Field(
        "mobu",
        title="Name of application",
        description="Doubles as the root HTTP endpoint path.",
    )

    path_prefix: str = Field(
        "/mobu",
        title="URL prefix for application API",
    )

    profile: Profile = Field(
        Profile.development,
        title="Application logging profile",
        validation_alias="MOBU_LOGGING_PROFILE",
    )

    log_level: LogLevel = Field(
        LogLevel.INFO,
        title="Log level of the application's logger",
    )

    metrics: MetricsConfiguration = Field(default_factory=MetricsConfiguration)

    model_config = SettingsConfigDict(
        env_prefix="MOBU_", env_nested_delimiter="__", case_sensitive=False
    )


config = Configuration()
"""Configuration for mobu."""
