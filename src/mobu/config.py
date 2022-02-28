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
    If not set or set to "None", this feature will be disabled.
    """

    autostart: Optional[str] = os.getenv("AUTOSTART")
    """The path to a YAML file defining what flocks to automatically start.

    The YAML file should, if given, be a list of flock specifications. All
    flocks specified there will be automatically started when mobu starts.
    """

    environment_url: str = os.getenv("ENVIRONMENT_URL", "")
    """The URL of the environment to run tests against.

    This is used for creating URLs to services, such as JupyterHub.
    mobu will not work if this is not set.

    Set with the ``ENVIRONMENT_URL`` environment variable.
    """

    cachemachine_image_policy: Optional[str] = os.getenv(
        "CACHEMACHINE_IMAGE_POLICY", "available"
    )
    """Whether to use the images available on all nodes, or the images
    desired by cachemachine.  In instances where image streaming is enabled,
    and therefore pulls are fast, ``desired`` is preferred.  The default is
    ``available``.

    Set with the ``CACHEMACHINE_IMAGE_POLICY`` environment variable.
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
