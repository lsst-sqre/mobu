"""Exceptions for mobu."""

from __future__ import annotations


class MonkeyNotFoundException(Exception):
    """The named monkey was not found."""

    def __init__(self, monkey: str) -> None:
        self.monkey = monkey
        super().__init__(f"Monkey {monkey} not found")


class NotebookException(Exception):
    """Passing an error back from a remote notebook session."""
