"""Data models for an authenticated user."""

import time
from typing import List

from aiohttp import ClientSession
from pydantic import BaseModel, Field

from ..config import config

__all__ = ["AuthenticatedUser", "UserConfig"]


class UserConfig(BaseModel):
    """Configuration for the user whose credentials the monkey will use."""

    username: str = Field(..., title="Username", example="testuser")

    uidnumber: int = Field(..., title="Numeric UID", example=60001)

    scopes: List[str] = Field(
        ...,
        title="Token scopes",
        description="Must include all scopes required to run the business",
        example=["exec:notebook", "read:tap"],
    )


class AuthenticatedUser(UserConfig):
    """Represents an authenticated user with a token."""

    token: str = Field(
        ...,
        title="Authentication token for user",
        example="gt-1PhgAeB-9Fsa-N1NhuTu_w.oRvMvAQp1bWfx8KCJKNohg",
    )

    @classmethod
    async def create(
        cls, user_config: UserConfig, session: ClientSession
    ) -> "AuthenticatedUser":
        token_url = f"{config.environment_url}/auth/api/v1/tokens"
        r = await session.post(
            token_url,
            headers={"Authorization": f"Bearer {config.gafaelfawr_token}"},
            json={
                "username": user_config.username,
                "name": "Mobu Test User",
                "token_type": "user",
                "token_name": f"mobu {str(float(time.time()))}",
                "scopes": user_config.scopes,
                "expires": int(time.time() + 2419200),
                "uid": user_config.uidnumber,
            },
            raise_for_status=True,
        )
        body = await r.json()
        return cls(
            username=user_config.username,
            uidnumber=user_config.uidnumber,
            token=body["token"],
            scopes=user_config.scopes,
        )
