"""All the data for a mobu user."""

from __future__ import annotations

__all__ = [
    "User",
]

import time
from dataclasses import dataclass
from typing import List

from aiohttp import ClientSession

from mobu.config import Configuration


@dataclass
class User:
    username: str
    uidnumber: int
    token: str
    scopes: List[str]

    @classmethod
    async def create(
        cls, username: str, uidnumber: int, scopes: List[str]
    ) -> User:
        token = await cls.generate_token(username, uidnumber, scopes)
        return cls(
            username=username,
            uidnumber=uidnumber,
            token=token,
            scopes=scopes,
        )

    @classmethod
    async def generate_token(
        cls, username: str, uidnumber: int, scopes: List[str]
    ) -> str:
        token_url = f"{Configuration.environment_url}/auth/api/v1/tokens"
        admin_token = Configuration.gafaelfawr_token
        async with ClientSession() as s:
            r = await s.post(
                token_url,
                headers={"Authorization": f"bearer {admin_token}"},
                json={
                    "username": username,
                    "token_type": "user",
                    "token_name": f"mobu {str(int(time.time()))}",
                    "scopes": scopes,
                    "expires": int(time.time() + 2419200),
                    "uid": uidnumber,
                },
                raise_for_status=True,
            )
            body = await r.json()
            return body["token"]

    def dump(self) -> dict:
        return {
            "username": self.username,
            "uidnumber": self.uidnumber,
            "token": self.token,
        }
