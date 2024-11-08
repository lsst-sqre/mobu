"""Build test configuration for mobu."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "config_path",
]


def config_path(filename: str) -> Path:
    """Return the path to a test configuration file.

    Parameters
    ----------
    filename
        The base name of a test configuration file or template.

    Returns
    -------
    Path
        The path to that file.
    """
    return (
        Path(__file__).parent.parent / "data" / "config" / (filename + ".yaml")
    )
