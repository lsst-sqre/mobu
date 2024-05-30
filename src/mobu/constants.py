"""Global constants for mobu."""

from __future__ import annotations

from datetime import timedelta

__all__ = [
    "GITHUB_WEBHOOK_WAIT_SECONDS",
    "NOTEBOOK_REPO_URL",
    "NOTEBOOK_REPO_BRANCH",
    "TOKEN_LIFETIME",
    "USERNAME_REGEX",
    "WEBSOCKET_OPEN_TIMEOUT",
]

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
