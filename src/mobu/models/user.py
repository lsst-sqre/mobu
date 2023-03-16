"""Data models for an authenticated user."""

import time
from typing import Any, List, Optional

from aiohttp import ClientSession
from pydantic import BaseModel, Field

from ..config import config

__all__ = ["AuthenticatedUser", "User", "UserSpec"]


class User(BaseModel):
    """Configuration for the user whose credentials the monkey will use."""

    username: str = Field(..., title="Username", example="testuser")

    uidnumber: Optional[int] = Field(
        None,
        title="Numeric UID",
        description=(
            "If omitted, Gafaelfawr will assign a UID. (Gafaelfawr UID"
            " assignment requires Firestore be configured.)"
        ),
        example=60001,
    )

    gidnumber: Optional[int] = Field(
        None,
        title="Primary GID",
        description=(
            "If omitted but a UID was specified, use a GID equal to the UID."
            " If both are omitted, Gafaelfawr will assign a UID and GID."
            " (Gafaelfawr UID and GID assignment requires Firestore and"
            " synthetic user private groups to be configured.)"
        ),
        example=60001,
    )


class UserSpec(BaseModel):
    """Configuration to generate a set of users."""

    username_prefix: str = Field(
        ...,
        title="Prefix for usernames",
        description="Each user will be formed by appending a number to this",
        example="lsptestuser",
    )

    uid_start: Optional[int] = Field(
        None,
        title="Starting UID",
        description=(
            "Users will be given consecutive UIDs starting with this. If"
            " omitted, Gafaelfawr will assign UIDs. (Gafaelfawr UID assignment"
            " requires Firestore be configured.)"
        ),
        example=60000,
    )

    gid_start: Optional[int] = Field(
        None,
        title="Starting GID",
        description=(
            "Users will be given consecutive primary GIDs starting with this."
            " If omitted but UIDs were given, the GIDs will be equal to the"
            " UIDs. If both are omitted, Gafaelfawr will assign UIDs and GIDs"
            " (which requires Firestore and synthetic user private groups to"
            " be configured)."
        ),
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
        data: dict[str, Any] = {
            "username": user.username,
            "name": "Mobu Test User",
            "token_type": "user",
            "token_name": f"mobu {str(float(time.time()))}",
            "scopes": scopes,
            "expires": int(time.time() + 60 * 60 * 24 * 365),
        }
        if user.uidnumber is not None:
            data["uid"] = user.uidnumber
            if user.gidnumber is not None:
                data["gid"] = user.gidnumber
            else:
                data["gid"] = user.uidnumber
        elif user.gidnumber is not None:
            data["gid"] = user.gidnumber
        r = await session.post(
            token_url,
            headers={"Authorization": f"Bearer {config.gafaelfawr_token}"},
            json=data,
            raise_for_status=True,
        )
        body = await r.json()
        return cls(
            username=user.username,
            uidnumber=data["uid"] if "uid" in data else None,
            gidnumber=data["gid"] if "gid" in data else None,
            token=body["token"],
            scopes=scopes,
        )
