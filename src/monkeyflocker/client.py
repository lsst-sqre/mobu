#!/usr/bin/env python
"""This is the monkeyflocker client that actually talks to the mobu endpoint.
"""

import asyncio
import logging
import math
import os
import pathlib
import random
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
        responses: Dict[str, Dict[str, Optional[aiohttp.ClientResponse]]] = {}
        client = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.token, ""),
            headers={"Content-Type": "application/json"},
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=session_timeout),
            connector=aiohttp.TCPConnector(limit=0),
        )
        for u in self.users:
            if command == "start":
                url = self.endpoint
                payload = self.template.render(USERNAME=u.name, UID=u.uid)
                self.log.info(f"Requesting creation for {u.name}")
                await self._http_call_with_retry(
                    client, url=url, method="POST", data=payload
                )
            else:  # 'report' or 'stop'
                # Generate output on 'stop' too
                url = f"{self.endpoint}/{u.name}"
                self.log.info(f"Requesting log and stats for {u.name}")
                log_response = await self._http_call_with_retry(
                    client, url=f"{url}/log", method="GET"
                )
                stat_response = await self._http_call_with_retry(
                    client, url=url, method="GET"
                )
                responses[u.name] = {
                    "log": log_response,
                    "stat": stat_response,
                }
                await self._generate_output(responses)
        if command == "stop":
            # The delete retry processing is different
            await self._delete_user_batch(client)
        await client.close()

    async def _http_call_with_retry(
        self,
        client: aiohttp.ClientSession,
        url: str,
        method: str,
        data: Optional[str] = None,
    ) -> Optional[aiohttp.ClientResponse]:
        max_retries: int = 10
        count: int = 0
        delay: int = 1
        max_delay: int = 30
        while count < max_retries:
            if count != 0:
                logstr = f"Pausing {delay}s before retrying {method} {url}"
                if data:
                    logstr += f" with data {data}"
                self.log.info(logstr)
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            count += 1
            result = None
            try:
                result = await client.request(
                    url=url, method=method, data=data
                )
            except aiohttp.client_exceptions.ClientResponseError as exc:
                status = exc.status
                if status == 404 and method == "GET":
                    # Already deleted?  Probably OK.
                    return None
                self.log.error(
                    f"{method} {url} gave status [ {status} ]: {exc}"
                )
            except Exception as exc:
                self.log.error(f"{method} {url} -> {exc}")
            if result:
                return result
        self.log.error(
            f"{method} {url} did not succeed after {max_retries} attempts"
        )
        return None

    async def _delete_user_batch(self, client: aiohttp.ClientSession) -> None:
        # User deletion gets stuck a lot.  This is probably because the
        # Hub won't let you mess with users in mid-spawn, which is why you
        # sometimes(interactively) have to wait for a timeout.
        #
        # To mitigate that, we explicitly do all the deletions in parallel.
        max_delay: int = 30
        max_retries: int = 10
        count: int = 0
        delay: int = 1
        userlist: List[str] = [u.name for u in self.users]
        while count < max_retries:
            if not userlist:
                return  # We're done
            self.log.info(f"Attempting to delete users: {userlist}")
            if count != 0:
                self.log.info(
                    f"Pausing {delay}s before retrying deletion"
                    + f"[{1 + count}/{max_retries}]"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            count += 1
            reqs: List[Any] = []  # Not really Any but the types are spoopy
            for u in userlist:
                reqs.append(client.delete(url=f"{self.endpoint}/{u}"))
                # Don't overwhelm the endpoint
                await self._random_wait(userlist, max_delay)
            retry_users: List[str] = []
            results = await asyncio.gather(*reqs, return_exceptions=True)
            for idx, r in enumerate(results):
                ru = userlist[idx]
                if isinstance(r, Exception):
                    if isinstance(
                        r, aiohttp.client_exceptions.ClientResponseError
                    ):
                        if r.status != 404:
                            self.log.warning(f"Failed to delete {ru}: {r}")
                            retry_users.append(ru)
                        # A 404 means (probably) "already deleted".  Don't
                        # retry, it's OK-ish.
            userlist = retry_users
        self.log.error(
            f"Could not delete {userlist} after" + " {max_retries} attempts."
        )

    async def _random_wait(self, userlist: List[str], max_delay: int) -> None:
        if userlist and max_delay:
            max_interval: float = max(1.0, (max_delay / len(userlist)))
            await asyncio.sleep(random.uniform(0, max_interval))

    async def _generate_output(
        self, responses: Dict[str, Dict[str, Optional[aiohttp.ClientResponse]]]
    ) -> None:
        if not self.output or not responses:
            return
        pathlib.Path(self.output).mkdir(parents=True, exist_ok=True)
        for user in responses:
            logobj = responses[user]["log"]
            statobj = responses[user]["stat"]
            log: Optional[str] = None
            stat: Optional[str] = None
            if logobj is not None:
                log = await logobj.text()
            if statobj is not None:
                stat = await statobj.text()
            if log is not None:
                fname = os.path.join(self.output, f"{user}_log.txt")
                with open(fname, "w") as f:
                    f.write(log)
            if stat is not None:
                fname = os.path.join(self.output, f"{user}_stats.json")
                with open(fname, "w") as f:
                    f.write(stat)
