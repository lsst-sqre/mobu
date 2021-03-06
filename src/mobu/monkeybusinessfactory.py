"""Factory for monkeys and their business, creating them from HTTP requests."""

__all__ = [
    "MonkeyBusinessFactory",
]

from typing import Dict

from mobu.business import Business
from mobu.jupyterloginloop import JupyterLoginLoop
from mobu.jupyterpythonloop import JupyterPythonLoop
from mobu.monkey import Monkey
from mobu.notebookrunner import NotebookRunner
from mobu.querymonkey import QueryMonkey
from mobu.user import User


class MonkeyBusinessFactory:
    @staticmethod
    def create(body: Dict) -> Monkey:
        name = body["name"]
        business = body["business"]
        user = body["user"]
        options = body.get("options", {})

        username = user["username"]
        uidnumber = user["uidnumber"]

        u = User(username, uidnumber)
        m = Monkey(name, u, options)

        businesses = [
            Business,
            JupyterLoginLoop,
            JupyterPythonLoop,
            NotebookRunner,
            QueryMonkey,
        ]

        new_business = None

        for b in businesses:
            if business == b.__name__:
                new_business = b(m, options)

        if not new_business:
            raise ValueError(f"Unknown business {business}")

        m.assign_business(new_business)
        return m
