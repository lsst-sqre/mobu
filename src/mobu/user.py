"""All the data for a mobu user."""

from __future__ import annotations

__all__ = [
    "User",
]

import json
import os
import time
from dataclasses import dataclass
from string import Template
from typing import List

import jwt
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
        if not Configuration.gafaelfawr_token:
            return cls.generate_legacy_token(username, uidnumber, scopes)

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

    @staticmethod
    def generate_legacy_token(
        username: str, uidnumber: int, scopes: List[str]
    ) -> str:
        template_path = os.path.join(
            os.path.dirname(__file__), "static/jwt-template.json"
        )

        with open(template_path, "r") as f:
            token_template = Template(f.read())

        with open(Configuration.private_key_path, "r") as f:
            signing_key = f.read()

        current_time = int(time.time())

        token_data = {
            "environment_url": Configuration.environment_url,
            "username": username,
            "uidnumber": uidnumber,
            "issue_time": current_time,
            "expiration_time": current_time + 2419200,
            "scopes": " ".join(scopes),
        }

        token_dict = json.loads(token_template.substitute(token_data))
        return jwt.encode(
            token_dict,
            key=signing_key,
            headers={"kid": "reissuer"},
            algorithm="RS256",
        )

    def dump(self) -> dict:
        return {
            "username": self.username,
            "uidnumber": self.uidnumber,
            "token": self.token,
        }
