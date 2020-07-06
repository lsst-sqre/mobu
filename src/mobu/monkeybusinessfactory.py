"""Factory for monkeys and their business, creating them from HTTP requests."""

__all__ = [
    "MonkeyBusinessFactory",
]

from typing import Dict

from mobu.business import Business
from mobu.jupyterloginloop import JupyterLoginLoop
from mobu.jupyterpythonloop import JupyterPythonLoop
from mobu.monkey import Monkey
from mobu.querymonkey import QueryMonkey
from mobu.user import User


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

        businesses = [
            Business,
            JupyterLoginLoop,
            JupyterPythonLoop,
            QueryMonkey,
        ]

        new_business = None

        for b in businesses:
            if business == b.__name__:
                new_business = b(m)

        if not new_business:
            raise ValueError(f"Unknown business {business}")

        m.business = new_business
        return m
