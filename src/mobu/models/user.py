"""Data models for an authenticated user."""

import time
from typing import List

from aiohttp import ClientSession
from pydantic import BaseModel, Field

from ..config import config

__all__ = ["AuthenticatedUser", "User", "UserSpec"]


class User(BaseModel):
    """Configuration for the user whose credentials the monkey will use."""

    username: str = Field(..., title="Username", example="testuser")

    uidnumber: int = Field(..., title="Numeric UID", example=60001)


class UserSpec(BaseModel):
    """Configuration to generate a set of users."""

    username_prefix: str = Field(
        ...,
        title="Prefix for usernames",
        description="Each user will be formed by appending a number to this",
        example="lsptestuser",
    )

    uid_start: int = Field(
        ...,
        title="Starting UID",
        description="Users will be given consecutive UIDs starting with this",
        example=60000,
    )


class AuthenticatedUser(User):
    """Represents an authenticated user with a token."""

    scopes: List[str] = Field(
        ...,
        title="Token scopes",
        example=["exec:notebook", "read:tap"],
    )

    token: str = Field(
        ...,
        title="Authentication token for user",
        example="gt-1PhgAeB-9Fsa-N1NhuTu_w.oRvMvAQp1bWfx8KCJKNohg",
    )

    @classmethod
    async def create(
        cls, user: User, scopes: List[str], session: ClientSession
    ) -> "AuthenticatedUser":
        token_url = f"{config.environment_url}/auth/api/v1/tokens"
        r = await session.post(
            token_url,
            headers={"Authorization": f"Bearer {config.gafaelfawr_token}"},
            json={
                "username": user.username,
                "name": "Mobu Test User",
                "token_type": "user",
                "token_name": f"mobu {str(float(time.time()))}",
                "scopes": scopes,
                "expires": int(time.time() + 60 * 60 * 24 * 365),
                "uid": user.uidnumber,
            },
            raise_for_status=True,
        )
        body = await r.json()
        return cls(
            username=user.username,
            uidnumber=user.uidnumber,
            token=body["token"],
            scopes=scopes,
        )
