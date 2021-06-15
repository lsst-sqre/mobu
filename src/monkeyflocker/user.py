#!/usr/bin/env python
"""The MonkeyflockerUser has two fields: name and uid.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MonkeyflockerUser:
    name: str
    uid: int
