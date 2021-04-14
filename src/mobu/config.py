"""Configuration definition."""

__all__ = ["Configuration"]

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Configuration:
    """Configuration for mobu."""

    alert_hook: str = os.getenv("ALERT_HOOK", "None")
    """The slack webhook used for alerting exceptions to slack.

    Set with the ``ALERT_HOOK`` environment variable.
    This is an https URL which should be considered secret.
    "None" may be provided in a secret to disable this feature.
    """

    private_key_path: str = os.getenv(
        "PRIVATE_KEY_PATH", "/etc/keys/signing_key.pem"
    )
    """The private key used for creating JWT tokens.

    Set with the ``PRIVATE_KEY_PATH`` environment variable.
    """

    environment_url: str = os.getenv(
        "ENVIRONMENT_URL", "https://nublado.lsst.codes"
    )
    """The URL of the environment to run tests against.

    This is used for creating URLs to services, such as nublado, as
    well as fields in the JWT ticket.

    Set with the ``ENVIRONMENT_URL`` environment variable.
    """

    gafaelfawr_token: Optional[str] = os.getenv("GAFAELFAWR_TOKEN", None)
    """The Gafaelfawr admin token to use to create user tokens.

    If set, this token is used to make an admin API call to Gafaelfawr to get
    a token for the user.

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
