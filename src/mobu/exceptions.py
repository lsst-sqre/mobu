"""Exceptions for mobu."""

from __future__ import annotations


class FlockNotFoundException(Exception):
    """The named flock was not found."""

    def __init__(self, flock: str) -> None:
        self.flock = flock
        super().__init__(f"Flock {flock} not found")


class MonkeyNotFoundException(Exception):
    """The named monkey was not found."""

    def __init__(self, monkey: str) -> None:
        self.monkey = monkey
        super().__init__(f"Monkey {monkey} not found")


class NotebookException(Exception):
    """Passing an error back from a remote notebook session."""
