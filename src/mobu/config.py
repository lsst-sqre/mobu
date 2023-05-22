"""Configuration definition."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseSettings, Field, HttpUrl
from safir.logging import LogLevel, Profile

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
        env="ALERT_HOOK",
        example="https://slack.example.com/ADFAW1452DAF41/",
    )

    autostart: Path | None = Field(
        None,
        title="Path to YAML file defining flocks to automatically start",
        description=(
            "If given, the YAML file must contain a list of flock"
            " specifications. All flocks given there will be automatically"
            " started when mobu starts."
        ),
        env="AUTOSTART",
        example="/etc/mobu/autostart.yaml",
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
        env="ENVIRONMENT_URL",
        example="https://data.example.org/",
    )

    gafaelfawr_token: str | None = Field(
        None,
        field="Gafaelfawr admin token used to create user tokens",
        description=(
            "This token is used to make an admin API call to Gafaelfawr to"
            " get a token for the user. This is only optional to make writing"
            " tests easier. mobu will abort during startup if it is not set."
        ),
        env="GAFAELFAWR_TOKEN",
        example="gt-vilSCi1ifK_MyuaQgMD2dQ.d6SIJhowv5Hs3GvujOyUig",
    )

    name: str = Field(
        "mobu",
        title="Name of application",
        description="Doubles as the root HTTP endpoint path.",
        env="SAFIR_NAME",
    )

    path_prefix: str = Field(
        "/mobu",
        title="URL prefix for application API",
        env="SAFIR_PATH_PREFIX",
    )

    profile: Profile = Field(
        Profile.development,
        title="Application logging profile",
        env="SAFIR_PROFILE",
    )

    log_level: LogLevel = Field(
        LogLevel.INFO,
        title="Log level of the application's logger",
        env="SAFIR_LOG_LEVEL",
    )


config = Configuration()
"""Configuration for mobu."""
