"""All the data for a sciencemonkey user."""

__all__ = [
    "User",
]

import asyncio
from dataclasses import dataclass


@dataclass
class User:
    username: str
    uidnumber: int
