"""Factory for monkeys and their business, creating them from HTTP requests."""

__all__ = [
    "MonkeyBusinessFactory",
]

from typing import Dict

from mobu.business.base import Business
from mobu.business.businesstime import BusinessTime
from mobu.business.jupyterjitterloginloop import JupyterJitterLoginLoop
from mobu.business.jupyterloginloop import JupyterLoginLoop
from mobu.business.jupyterpythonloop import JupyterPythonLoop
from mobu.business.notebookrunner import NotebookRunner
from mobu.business.querymonkey import QueryMonkey
from mobu.monkey import Monkey
from mobu.user import User


class MonkeyBusinessFactory:
    @staticmethod
    async def create(body: Dict) -> Monkey:
        name = body["name"]
        business = body["business"]
        user = body["user"]
        options = body.get("options", {})

        username = user["username"]
        uidnumber = user["uidnumber"]
        scopes = user["scopes"]

        u = await User.create(username, uidnumber, scopes)
        m = Monkey(name, u, options)

        businesses = [
            Business,
            BusinessTime,
            JupyterLoginLoop,
            JupyterJitterLoginLoop,
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
