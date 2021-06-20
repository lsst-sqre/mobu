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
from typing import Any, Dict, List, Optional

import aiohttp
import jinja2
import structlog
from structlog._config import BoundLoggerLazyProxy

from .user import MonkeyflockerUser as MFUser

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class ShadowRequest:
    """This contains method, url, username, and body, if any.
    Retrieving it from the actual request turns out to be tricky because
    it's really a morass of little internal _*RequestContextManager objects.
    """

    method: str
    url: str
    username: str
    data: Optional[str]


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
        numdigits = max(2, int(math.log10(count)) + 1)
        r = range(1, (count + 1))
        for n in r:
            name = "{}{:0>{}d}".format(base_username, n, numdigits)
            uid = base_uid + n
            userlist.append(MFUser(name=name, uid=uid))
        return userlist

    async def execute(self, command: str) -> None:
        session_timeout = 30
        requests = []
        shadow_requests: List[ShadowRequest] = []
        client = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.token, ""),
            headers={"Content-Type": "application/json"},
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=session_timeout),
        )
        for u in self.users:
            if command == "start":
                url = self.endpoint
                payload = self.template.render(USERNAME=u.name, UID=u.uid)
                requests.append(client.post(url=url, data=payload))
                shadow_requests.append(
                    ShadowRequest(
                        url=url, username=u.name, method="POST", data=payload
                    )
                )
            else:
                # Generate output on 'stop' too
                url = f"{self.endpoint}/{u.name}"
                requests.append(client.get(url=f"{url}/log"))
                shadow_requests.append(
                    ShadowRequest(
                        url=f"{url}/log",
                        username=u.name,
                        method="GET",
                        data=None,
                    )
                )
                requests.append(client.get(url=url))
                shadow_requests.append(
                    ShadowRequest(
                        url=url, username=u.name, method="GET", data=None
                    )
                )

        if command == "stop":
            # We want to stack all the deletes at the end, rather than
            # interleaving
            for u in self.users:
                requests.append(client.delete(url=f"{self.endpoint}/{u.name}"))
                shadow_requests.append(
                    ShadowRequest(
                        url=url, username=u.name, method="DELETE", data=None
                    )
                )

        output = await self._retry_requests(client, requests, shadow_requests)
        if command == "report" or command == "stop":
            await self._generate_output(output)
        await client.close()

    async def _retry_requests(
        self,
        client: aiohttp.ClientSession,
        requests: List[Any],
        shadow_requests: List[ShadowRequest],
    ) -> Dict[str, str]:
        returned_text: Dict[str, str] = {}
        delay: int = 1
        max_delay: int = 30
        max_tries: int = 10
        count = 0
        while count < max_tries:
            if count != 0:
                self.log.info(
                    f"Waiting {delay}s before retrying failed requests"
                    + f" {count}/{max_tries}"
                )
                await asyncio.sleep(delay)
                delay *= 2
                if delay > max_delay:
                    delay = max_delay
            count += 1
            results = []
            try:
                results = await asyncio.gather(
                    *requests, return_exceptions=True
                )
            except TypeError as exc:
                self.log.error(
                    "TypeError trying to gather something vile:" + f" {exc}."
                )
            retry = []
            for idx, res in enumerate(results):
                shadow = shadow_requests[idx]
                method = shadow.method
                url = shadow.url
                data = shadow.data
                username = shadow.username
                if isinstance(res, Exception):
                    if (res.status != 404) or (
                        method not in ["DELETE", "GET"]
                    ):
                        # 404 from DELETE or GET is OK-ish
                        # Probably means "already deleted"
                        self.log.warning(
                            f"{username}: {method} {url} -> {res}"
                        )
                        logstr: str = f"Retry for {username}: {method} {url}"
                        if data:
                            logstr += f" with data {data}"
                        self.log.warning(logstr)
                        retry.append(
                            client.request(method=method, url=url, data=data)
                        )
                else:
                    if method == "GET":
                        # We only care about returned text from our
                        #  GET requests
                        try:
                            returned_text[url] = await res.text()
                        except Exception as exc:
                            self.log.warning(
                                f"Could not get text of response: {exc}"
                            )
            requests = retry
            if not retry:
                break
        if count >= max_tries:
            self.log.warning(f"Giving up after {max_tries} retries.")
        return returned_text

    async def _generate_output(self, results: Dict[str, str]) -> None:
        if not self.output or not results:
            return
        pathlib.Path(self.output).mkdir(parents=True, exist_ok=True)
        for url in results:
            content = results.get(url)
            if not content:
                return
            # Pick output filename
            suffix = "stats.json"
            user = url[len(self.endpoint) + 1 :]
            if user.endswith("/log"):
                user = user[:-4]
                suffix = "log.txt"
            fname = os.path.join(self.output, f"{user}_{suffix}")
            with open(fname, "w") as f:
                f.write(content)
