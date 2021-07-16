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

from aiohttp import ClientResponseError, ClientSession, TCPConnector
from structlog._config import BoundLoggerLazyProxy

from mobu.config import Configuration
from mobu.user import User


class NotebookException(Exception):
    """Passing an error back from a remote notebook session."""

    pass


class AuthException(ClientResponseError):
    """Wrapper for 401 and 403 auth errors."""

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

        self.session = ClientSession(
            headers=self.headers, connector=TCPConnector(limit=10000)
        )
        self.session.cookie_jar.update_cookies(
            BaseCookie({"_xsrf": self.xsrftoken})
        )

    __ansi_reg_exp = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")

    @classmethod
    def _ansi_escape(cls, line: str) -> str:
        return cls.__ansi_reg_exp.sub("", line)

    async def hub_login(self) -> None:
        try:
            await self.session.get(
                self.jupyter_url + "hub/login", raise_for_status=True
            )
        except ClientResponseError as exc:
            await self.handle_error("hub login", exc)

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
        try:
            await self.session.get(lab_url, raise_for_status=True)
        except ClientResponseError as exc:
            await self.handle_error("lab login", exc)

    async def is_lab_running(self) -> bool:
        self.log.info("Is lab running?")
        hub_url = self.jupyter_url + "hub"
        try:
            r = await self.session.get(hub_url)
        except ClientResponseError as exc:
            await self.handle_error("lab run check", exc)
        if r.status != 200:
            self.log.error(f"Unexpected status {r.status} from {r.url}")
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
        try:
            r = await self.session.get(spawn_url)
        except ClientResponseError as exc:
            await self.handle_error("spawn lab (get)", exc)
        await r.text()

        try:
            r = await self.session.post(
                spawn_url,
                data=self.jupyter_options_form,
                allow_redirects=False,
                raise_for_status=True,
            )
        except ClientResponseError as exc:
            await self.handle_error("spawn lab (redirect)", exc)

        if r.status != 302:
            raise Exception(f"Error: spawn {r.url} did not redirect")
        redirect_url = (
            self.jupyter_base + f"hub/spawn-pending/{self.user.username}"
        )
        if r.headers["Location"] != redirect_url:
            raise Exception(
                f"Spawn didn't redirect to pending: {r.headers}: {r}"
            )

        # Jupyterlab will give up a spawn after 900 seconds, so we shouldn't
        # wait longer than that.
        max_poll_secs = 900
        poll_interval = 15
        retries = max_poll_secs / poll_interval

        while retries > 0:
            try:
                r = await self.session.get(pending_url, raise_for_status=True)
            except ClientResponseError as exc:
                await self.handle_error("spawn", exc)
            if str(r.url) == lab_url:
                self.log.info(f"Lab spawned, redirected to {r.url}")
                return

            self.log.info(f"Still waiting for lab to spawn [{r.status}]")
            retries -= 1
            await asyncio.sleep(poll_interval)

        raise Exception("Giving up waiting for lab to spawn!")

    async def delete_lab(self) -> None:
        headers = {"Referer": self.jupyter_url + "hub/home"}

        server_url = (
            self.jupyter_url + f"hub/api/users/{self.user.username}/server"
        )
        self.log.info(f"Deleting lab for {self.user.username} at {server_url}")

        try:
            r = await self.session.delete(
                server_url, headers=headers, raise_for_status=True
            )
        except ClientResponseError as exc:
            await self.handle_error("delete lab", exc)
        if r.status not in (200, 202, 204):
            raise Exception(f"Unexpected status {r.status} deleting lab: {r}")

    async def create_kernel(self, kernel_name: str = "LSST") -> str:
        kernel_url = (
            self.jupyter_url + f"user/{self.user.username}/api/kernels"
        )
        body = {"name": kernel_name}
        try:
            r = await self.session.post(
                kernel_url, json=body, raise_for_status=True
            )
        except ClientResponseError as exc:
            await self.handle_error("create_kernel", exc)
        if r.status != 201:
            raise Exception(
                f"Unexpected status creating kernel: {r.status} : {r}"
            )
        response = await r.json()
        return response["id"]

    async def delete_kernel(self, kernel_id: str) -> None:
        kernel_url = (
            self.jupyter_url
            + f"user/{self.user.username}/api/kernels/{kernel_id}"
        )
        try:
            r = await self.session.delete(kernel_url, raise_for_status=True)
        except ClientResponseError as exc:
            await self.handle_error("delete kernel", exc)
        if r.status != 204:
            self.log.warning(
                f"Delete kernel {kernel_id}: unexpected status"
                + f"{r.status}: {r}"
            )
        return

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

        try:
            async with self.session.ws_connect(kernel_url) as ws:
                await ws.send_json(msg)

                while True:
                    r = await ws.receive_json()
                    self.log.debug(f"Recieved kernel message: {r}")
                    msg_type = r["msg_type"]
                    if msg_type == "error":
                        error_message = "".join(r["content"]["traceback"])
                        raise NotebookException(
                            self._ansi_escape(error_message)
                        )
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
        except ClientResponseError as exc:
            await self.handle_error("ws_connect", exc)
        return ""

    def dump(self) -> dict:
        return {
            "cookies": [str(cookie) for cookie in self.session.cookie_jar],
        }

    async def handle_error(self, msg: str, exc: ClientResponseError) -> None:
        if exc.status == 403 or exc.status == 401:
            await self.handle_auth_error(msg, exc)
            return
        self._logerror("Error", msg, exc)
        raise exc

    async def handle_auth_error(
        self, msg: str, exc: ClientResponseError
    ) -> None:
        # We think that just connecting to "/hub/login" may do all the auth
        #  refresh we need.  Try that.
        self._logerror("Authentication Error", msg, exc)
        await self.hub_login()
        failed_request = exc.request_info
        self.log.info(
            f"Refreshed hub login, now resubmitting {failed_request}"
        )
        # If this fails again, raise the resulting exception, which SHOULD
        #  look like the original failed one, just a little delayed.
        # If not, keep going.
        await self.session.request(
            url=failed_request.real_url,
            method=failed_request.method,
            raise_for_status=True,
        )

    async def _logerror(
        self, mtype: str, msg: str, r: ClientResponseError
    ) -> None:
        rstr = f"{mtype}: {msg} [{r.status}]: {r.request_info.url}"
        rstr += f"(Headers: {r.headers}) {r.message} -> {r}"
        self.log.error(rstr)
