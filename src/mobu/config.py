"""Configuration definition."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

__all__ = ["Configuration", "config"]


@dataclass
class Configuration:
    """Configuration for mobu."""

    alert_hook: Optional[str] = os.getenv("ALERT_HOOK")
    """The slack webhook used for alerting exceptions to slack.

    Set with the ``ALERT_HOOK`` environment variable.
    This is an https URL which should be considered secret.
    If not set, this feature will be disabled.
    """

    environment_url: str = os.getenv("ENVIRONMENT_URL", "")
    """The URL of the environment to run tests against.

    This is used for creating URLs to services, such as JupyterHub.
    mobu will not work if this is not set.

    Set with the ``ENVIRONMENT_URL`` environment variable.
    """

    gafaelfawr_token: Optional[str] = os.getenv("GAFAELFAWR_TOKEN")
    """The Gafaelfawr admin token to use to create user tokens.

    This token is used to make an admin API call to Gafaelfawr to get a token
    for the user.  mobu will not work if this is not set.

    Set with the ``GAFAELFAWR_TOKEN`` environment variable.
    """

    name: str = os.getenv("SAFIR_NAME", "mobu")
    """The application's name, which doubles as the root HTTP endpoint path.

    Set with the ``SAFIR_NAME`` environment variable.
    """

    profile: str = os.getenv("SAFIR_PROFILE", "development")
    """Application run profile: "development" or "production".

    Set with the ``SAFIR_PROFILE`` environment variable.
    """

    logger_name: str = os.getenv("SAFIR_LOGGER", "mobu")
    """The root name of the application's logger.

    Set with the ``SAFIR_LOGGER`` environment variable.
    """

    log_level: str = os.getenv("SAFIR_LOG_LEVEL", "INFO")
    """The log level of the application's logger.

    Set with the ``SAFIR_LOG_LEVEL`` environment variable.
    """


config = Configuration()
"""Configuration for mobu."""
