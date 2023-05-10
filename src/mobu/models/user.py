"""Data models for an authenticated user."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

__all__ = [
    "AuthenticatedUser",
    "User",
    "UserSpec",
]


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

    scopes: list[str] = Field(
        ...,
        title="Token scopes",
        example=["exec:notebook", "read:tap"],
    )

    token: str = Field(
        ...,
        title="Authentication token for user",
        example="gt-1PhgAeB-9Fsa-N1NhuTu_w.oRvMvAQp1bWfx8KCJKNohg",
    )
