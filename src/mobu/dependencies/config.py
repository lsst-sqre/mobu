"""Config dependency."""

import os
from pathlib import Path

from ..config import Configuration
from ..constants import CONFIGURATION_PATH

__all__ = [
    "ConfigDependency",
    "config_dependency",
]


class ConfigDependency:
    """Dependency to manage a cached Mobu configuration.

    The controller configuration is read on first request, cached, and
    returned to all dependency callers unless `~ConfigDependency.set_path` is
    called to change the configuration.

    Parameters
    ----------
    path
        Path to the Nublado mobu configuration.
    """

    def __init__(self, path: Path = CONFIGURATION_PATH) -> None:
        # This is needed for running mobu locally, and in unit tests, to
        # specify an alternate config file when mobu is started in a separate
        # process from the tests.
        if test_path := os.environ.get("MOBU_CONFIG_PATH"):
            path = Path(test_path)
        self._path = path
        self._config: Configuration | None = None

    async def __call__(self) -> Configuration:
        return self.config

    @property
    def config(self) -> Configuration:
        """Load configuration if needed and return it."""
        if self._config is None:
            self._config = Configuration.from_file(self._path)
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Whether the configuration has been initialized."""
        return self._config is not None

    def set_path(self, path: Path) -> None:
        """Change the configuration path and reload.

        Parameters
        ----------
        path
            New configuration path.
        """
        self._path = path
        self._config = Configuration.from_file(path)


config_dependency = ConfigDependency()
"""The dependency that will return the global configuration."""
