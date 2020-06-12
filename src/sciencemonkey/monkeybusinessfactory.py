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
from sciencemonkey.user import User


class MonkeyBusinessFactory:
    @staticmethod
    def create(body: Dict) -> Business:
        username = body["username"]
        uidnumber = body["uidnumber"]
        business = body.get("business", None)

        u = User(username, uidnumber)

        if business is None:
            b = Business(u)
        elif business == "JupyterLoginLoop":
            b = JupyterLoginLoop(u)
        elif business == "JupyterPythonLoop":
            b = JupyterPythonLoop(u)
        else:
            raise ValueError(f"Unknown business {business}")

        return b
