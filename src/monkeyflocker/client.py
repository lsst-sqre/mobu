#!/usr/bin/env python
"""This is the monkeyflocker client that actually talks to the mobu endpoint.
"""

import asyncio
import logging
import math
import os
import pathlib
import sys
from dataclasses import InitVar, dataclass, field
from typing import List

import aiohttp
import jinja2
import structlog
from structlog._config import BoundLoggerLazyProxy

from .user import MonkeyflockerUser as MFUser

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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
    output: str
    users: List[MFUser] = field(init=False)
    log: BoundLoggerLazyProxy = field(init=False)

    def __post_init__(
        self, count: int, base_username: str, base_uid: int
    ) -> None:
        self.users = self._make_userlist(count, base_username, base_uid)
        self._initialize_logging()

    def _initialize_logging(self) -> None:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(message)s", datefmt=DATE_FORMAT
        )
        streamHandler = logging.StreamHandler(stream=sys.stdout)
        streamHandler.setFormatter(formatter)
        logger = logging.getLogger("Monkeyflocker")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(streamHandler)
        self.log = structlog.wrap_logger(logger)

    @staticmethod
    def _make_userlist(
        count: int, base_username: str, base_uid: int
    ) -> List[MFUser]:
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
            raise_for_status=True,
        )
        for u in self.users:
            if (command == "report") or (command == "stop"):
                await self.generate_output(client)
            if command == "report":
                continue
            if command == "start":
                payload = self.template.render(USERNAME=u.name, UID=u.uid)
                t = client.post(url=self.endpoint, data=payload)
            else:
                t = client.delete(url=f"{self.endpoint}/{u.name}")
            r.append(t)
        if r:
            results = await asyncio.gather(*r, return_exceptions=True)
            for res in results:
                # We are only using this to log errors
                _ = await self._result_to_string(res)
        await client.close()

    async def generate_output(self, client: aiohttp.ClientSession) -> None:
        if not self.output:
            return
        r = []
        pathlib.Path(self.output).mkdir(parents=True, exist_ok=True)
        for u in self.users:
            url = f"{self.endpoint}/{u.name}"
            r.append(client.get(url=f"{url}/log"))
            r.append(client.get(url=url))
        out = await asyncio.gather(*r, return_exceptions=True)
        idx: int = 0
        for u in self.users:
            # The output will be in the same order.  For each user, log, then
            #  stats
            lfile = os.path.join(self.output, f"{u.name}_log.txt")
            sfile = os.path.join(self.output, f"{u.name}_stats.json")
            log = out[idx]
            stat = out[idx + 1]
            with open(lfile, "w") as lf:
                lf.write(await self._result_to_string(log))
            with open(sfile, "w") as sf:
                sf.write(await self._result_to_string(stat))
            idx += 2

    async def _result_to_string(self, result: aiohttp.ClientResponse) -> str:
        if isinstance(result, Exception):
            self.log.error(f"{result}")
            return f"{result}"
        else:
            return await result.text()
