"""All the data for a mobu user."""

from __future__ import annotations

__all__ = [
    "User",
]

import time
from dataclasses import dataclass
from typing import List

from aiohttp import ClientSession

from mobu.config import config


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
        token_url = f"{config.environment_url}/auth/api/v1/tokens"
        async with ClientSession() as s:
            r = await s.post(
                token_url,
                headers={"Authorization": f"Bearer {config.gafaelfawr_token}"},
                json={
                    "username": username,
                    "token_type": "user",
                    "token_name": f"mobu {str(float(time.time()))}",
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
