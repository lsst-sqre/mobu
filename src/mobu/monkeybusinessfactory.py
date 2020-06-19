"""Factory for monkeys and their business, creating them from HTTP requests."""

__all__ = [
    "MonkeyBusinessFactory",
]

from typing import Dict

from sciencemonkey.business import (
    Business,
    JupyterLoginLoop,
    JupyterPythonLoop,
)
from sciencemonkey.monkey import Monkey
from sciencemonkey.user import User


class MonkeyBusinessFactory:
    @staticmethod
    def create(body: Dict) -> Monkey:
        username = body["username"]
        uidnumber = body["uidnumber"]
        business = body.get("business", None)
        restart = body.get("restart", False)

        u = User(username, uidnumber)
        m = Monkey(u)
        m.restart = restart

        if business is None:
            m.business = Business(m)
        elif business == "JupyterLoginLoop":
            m.business = JupyterLoginLoop(m)
        elif business == "JupyterPythonLoop":
            m.business = JupyterPythonLoop(m)
        else:
            raise ValueError(f"Unknown business {business}")

        return m
