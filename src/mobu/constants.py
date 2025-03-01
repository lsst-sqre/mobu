"""Global constants for mobu."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

__all__ = [
    "CONFIGURATION_PATH",
    "GITHUB_REPO_CONFIG_PATH",
    "GITHUB_WEBHOOK_WAIT_SECONDS",
    "NOTEBOOK_REPO_BRANCH",
    "NOTEBOOK_REPO_URL",
    "TOKEN_LIFETIME",
    "USERNAME_REGEX",
    "WEBSOCKET_OPEN_TIMEOUT",
]

CONFIGURATION_PATH = Path("/etc/mobu/config.yaml")
"""Default path to configuration."""

GITHUB_REPO_CONFIG_PATH = Path("mobu.yaml")
"""The path to a config file with repo-specific configuration."""

GITHUB_WEBHOOK_WAIT_SECONDS = 1
"""GithHub needs some time to actually be in the state in a webhook payload."""

NOTEBOOK_REPO_URL = "https://github.com/lsst-sqre/notebook-demo.git"
"""Default notebook repository for NotebookRunner."""

NOTEBOOK_REPO_BRANCH = "prod"
"""Default repository branch for NotebookRunner."""

TOKEN_LIFETIME = timedelta(days=365)
"""Token lifetime for mobu's service tokens.

mobu currently has no mechanism for refreshing tokens while running, so this
should be long enough that mobu will be restarted before the tokens expire.
An expiration exists primarily to ensure that the tokens don't accumulate
forever.
"""

WEBSOCKET_OPEN_TIMEOUT = 60
"""How long to wait for a WebSocket connection to open (in seconds)."""

# This must be kept in sync with Gafaelfawr until we can import the models
# from Gafaelfawr directly.
USERNAME_REGEX = (
    "^[a-z0-9](?:[a-z0-9]|-[a-z0-9])*[a-z](?:[a-z0-9]|-[a-z0-9])*$"
)
"""Regex matching all valid usernames."""

SENTRY_ERRORED_KEY = "errored"
"""Tag name to set on transactions that had exceptions."""
