#!/usr/bin/env python
"""This is the monkeyflocker client that actually talks to the mobu endpoint.
"""

import asyncio
import math
from dataclasses import InitVar, dataclass, field
from typing import List

import aiohttp
import jinja2

from .user import MonkeyflockerUser as MFUser


@dataclass
class MonkeyflockerClient:
    """This communicates with a mobu instance to create or destroy a
    troop of mobu workers"""

    count: InitVar[int]
    base_username: InitVar[str]
    base_uid: InitVar[int]
    endpoint: str
    token: str
    template: jinja2.Template
    users: List[MFUser] = field(init=False)

    def __post_init__(self, count, base_username, base_uid) -> None:
        self.users = self._make_userlist(count, base_username, base_uid)

    @staticmethod
    def _make_userlist(count, base_username, base_uid) -> List[MFUser]:
        userlist: List[MFUser] = []
        numdigits = max(2, int(math.log10(count)))
        r = range(1, (count + 1))
        for n in r:
            name = "{}{:0>{}d}".format(base_username, n, numdigits)
            uid = base_uid + n
            userlist.append(MFUser(name=name, uid=uid))
        return userlist

    async def execute(self, command: str) -> None:
        r = []
        client = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.token, ""),
            headers={"Content-Type": "application/json"},
        )
        for u in self.users:
            if command == "start":
                payload = self.template.render(USERNAME=u.name, UID=u.uid)
                t = client.post(url=self.endpoint, data=payload)
            else:
                t = client.delete(url=f"{self.endpoint}/{u.name}")
            r.append(t)
        await asyncio.gather(*r)
        await client.close()
