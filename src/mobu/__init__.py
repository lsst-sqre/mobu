"""The mobu service."""

__all__ = ["__version__", "metadata"]

from importlib.metadata import PackageNotFoundError, version

__version__: str
"""The application version string of (PEP 440 / SemVer compatible)."""

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"
