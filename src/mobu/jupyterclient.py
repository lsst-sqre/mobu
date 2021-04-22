"""AsyncIO client for communicating with Jupyter.

Allows the caller to login to the hub, spawn lab
containers, and then run jupyter kernels remotely."""

__all__ = [
    "JupyterClient",
]

import asyncio
import random
import re
import string
from dataclasses import dataclass
from http.cookies import BaseCookie
from typing import Any, Dict
from uuid import uuid4

from aiohttp import ClientResponse, ClientSession
from structlog._config import BoundLoggerLazyProxy

from mobu.config import Configuration
from mobu.user import User


class NotebookException(Exception):
    """Passing an error back from a remote notebook session."""

    pass


@dataclass
class JupyterClient:
    log: BoundLoggerLazyProxy
    user: User
    session: ClientSession
    headers: Dict[str, str]
    xsrftoken: str
    jupyter_url: str

    def __init__(
        self, user: User, log: BoundLoggerLazyProxy, options: Dict[str, Any]
    ):
        self.user = user
        self.log = log
        self.jupyter_base = options.get("nb_url", "/nb/")
        self.jupyter_url = Configuration.environment_url + self.jupyter_base

        self.xsrftoken = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=16)
        )
        self.jupyter_options_form = options.get("jupyter_options_form", {})

        self.headers = {
            "Authorization": "Bearer " + user.token,
            "x-xsrftoken": self.xsrftoken,
        }

        self.session = ClientSession(headers=self.headers)
        self.session.cookie_jar.update_cookies(
            BaseCookie({"_xsrf": self.xsrftoken})
        )

    __ansi_reg_exp = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")

    @classmethod
    def _ansi_escape(cls, line: str) -> str:
        return cls.__ansi_reg_exp.sub("", line)

    async def hub_login(self) -> None:
        async with self.session.get(self.jupyter_url + "hub/login") as r:
            if r.status != 200:
                await self._raise_error("Error logging into hub", r)

    async def ensure_lab(self) -> None:
        self.log.info("Ensure lab")
        running = await self.is_lab_running()
        if running:
            await self.lab_login()
        else:
            await self.spawn_lab()

    async def lab_login(self) -> None:
        self.log.info("Logging into lab")
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"
        async with self.session.get(lab_url) as r:
            if r.status != 200:
                await self._raise_error("Error logging into lab", r)

    async def is_lab_running(self) -> bool:
        self.log.info("Is lab running?")
        hub_url = self.jupyter_url + "hub"
        async with self.session.get(hub_url) as r:
            if r.status != 200:
                self.log.error(f"Error {r.status} from {r.url}")

            spawn_url = self.jupyter_url + "hub/spawn"
            self.log.info(f"Going to {hub_url} redirected to {r.url}")
            if str(r.url) == spawn_url:
                return False

        return True

    async def spawn_lab(self) -> None:
        spawn_url = self.jupyter_url + "hub/spawn"
        pending_url = (
            self.jupyter_url + f"hub/spawn-pending/{self.user.username}"
        )
        lab_url = self.jupyter_url + f"user/{self.user.username}/lab"

        # DM-23864: Do a get on the spawn URL even if I don't have to.
        async with self.session.get(spawn_url) as r:
            await r.text()

        async with self.session.post(
            spawn_url, data=self.jupyter_options_form, allow_redirects=False
        ) as r:
            if r.status != 302:
                await self._raise_error("Spawn did not redirect", r)

            redirect_url = (
                self.jupyter_base + f"hub/spawn-pending/{self.user.username}"
            )
            if r.headers["Location"] != redirect_url:
                await self._raise_error("Spawn didn't redirect to pending", r)

        # Jupyterlab will give up a spawn after 900 seconds, so we shouldn't
        # wait longer than that.
        max_poll_secs = 900
        poll_interval = 15
        retries = max_poll_secs / poll_interval

        while retries > 0:
            async with self.session.get(pending_url) as r:
                if str(r.url) == lab_url:
                    self.log.info(f"Lab spawned, redirected to {r.url}")
                    return

                if not r.ok:
                    await self._raise_error("Error spawning", r)

                self.log.info(f"Still waiting for lab to spawn {r}")
                retries -= 1
                await asyncio.sleep(poll_interval)

        raise Exception("Giving up waiting for lab to spawn!")

    async def delete_lab(self) -> None:
        headers = {"Referer": self.jupyter_url + "hub/home"}

        server_url = (
            self.jupyter_url + f"hub/api/users/{self.user.username}/server"
        )
        self.log.info(f"Deleting lab for {self.user.username} at {server_url}")

        async with self.session.delete(server_url, headers=headers) as r:
            if r.status not in [200, 202, 204]:
                await self._raise_error("Error deleting lab", r)

    async def create_kernel(self, kernel_name: str = "LSST") -> str:
        kernel_url = (
            self.jupyter_url + f"user/{self.user.username}/api/kernels"
        )
        body = {"name": kernel_name}

        async with self.session.post(kernel_url, json=body) as r:
            if r.status != 201:
                await self._raise_error("Error creating kernel", r)

            response = await r.json()
            return response["id"]

    async def run_python(self, kernel_id: str, code: str) -> str:
        kernel_url = (
            self.jupyter_url
            + f"user/{self.user.username}/api/kernels/{kernel_id}/channels"
        )

        msg_id = uuid4().hex

        msg = {
            "header": {
                "username": "",
                "version": "5.0",
                "session": "",
                "msg_id": msg_id,
                "msg_type": "execute_request",
            },
            "parent_header": {},
            "channel": "shell",
            "content": {
                "code": code,
                "silent": False,
                "store_history": False,
                "user_expressions": {},
                "allow_stdin": False,
            },
            "metadata": {},
            "buffers": {},
        }

        async with self.session.ws_connect(kernel_url) as ws:
            await ws.send_json(msg)

            while True:
                r = await ws.receive_json()
                self.log.debug(f"Recieved kernel message: {r}")
                msg_type = r["msg_type"]
                if msg_type == "error":
                    error_message = "".join(r["content"]["traceback"])
                    raise NotebookException(self._ansi_escape(error_message))
                elif (
                    msg_type == "stream"
                    and msg_id == r["parent_header"]["msg_id"]
                ):
                    return r["content"]["text"]
                elif msg_type == "execute_reply":
                    status = r["content"]["status"]
                    if status == "ok":
                        return ""
                    else:
                        raise NotebookException(
                            f"Error content status is {status}"
                        )

    def dump(self) -> dict:
        return {
            "cookies": [str(cookie) for cookie in self.session.cookie_jar],
        }

    async def _raise_error(self, msg: str, r: ClientResponse) -> None:
        raise Exception(f"{msg}: {r.status} {r.url}: {r.headers}")
