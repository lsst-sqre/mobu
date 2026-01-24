"""Data models for an authenticated user."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "AuthenticatedUser",
    "Group",
    "User",
    "UserSpec",
]


class Group(BaseModel):
    """Configuration for the group memberships of a user."""

    name: str = Field(
        ...,
        title="Name of the group",
        examples=["g_special_users"],
        min_length=1,
    )

    id: int = Field(..., title="Numeric GID of the group", examples=[123181])


class User(BaseModel):
    """Configuration for the user whose credentials the monkey will use."""

    username: str = Field(
        ...,
        title="Username",
        description="Must start with 'bot-mobu'",
        pattern=r"^bot-mobu",
        examples=["bot-mobu-testuser"],
    )

    uidnumber: int | None = Field(
        None,
        title="Numeric UID",
        description=(
            "If omitted, Gafaelfawr will assign a UID. (Gafaelfawr UID"
            " assignment requires Firestore be configured.)"
        ),
        examples=[60001],
    )

    gidnumber: int | None = Field(
        None,
        title="Primary GID",
        description=(
            "If omitted but a UID was specified, use a GID equal to the UID."
            " If both are omitted, Gafaelfawr will assign a UID and GID."
            " (Gafaelfawr UID and GID assignment requires Firestore and"
            " synthetic user private groups to be configured.)"
        ),
        examples=[60001],
    )

    groups: list[Group] = Field(
        [],
        title="Groups",
        description="Groups of which the user is a member",
    )


class UserSpec(BaseModel):
    """Configuration to generate a set of users."""

    username_prefix: str = Field(
        ...,
        title="Prefix for usernames",
        description="Each user will be formed by appending a number to this",
        examples=["bot-mobu-lsptestuser"],
    )

    uid_start: int | None = Field(
        None,
        title="Starting UID",
        description=(
            "Users will be given consecutive UIDs starting with this. If"
            " omitted, Gafaelfawr will assign UIDs. (Gafaelfawr UID assignment"
            " requires Firestore be configured.)"
        ),
        examples=[60000],
    )

    gid_start: int | None = Field(
        None,
        title="Starting GID",
        description=(
            "Users will be given consecutive primary GIDs starting with this."
            " If omitted but UIDs were given, the GIDs will be equal to the"
            " UIDs. If both are omitted, Gafaelfawr will assign UIDs and GIDs"
            " (which requires Firestore and synthetic user private groups to"
            " be configured)."
        ),
        examples=[60000],
    )

    groups: list[Group] = Field(
        [],
        title="Groups",
        description="Groups of which each user is a member",
    )


class AuthenticatedUser(User):
    """Represents an authenticated user with a token."""

    scopes: list[str] = Field(
        ...,
        title="Token scopes",
        examples=[["exec:notebook", "read:tap"]],
    )

    token: str = Field(
        ...,
        title="Authentication token for user",
        examples=["gt-1PhgAeB-9Fsa-N1NhuTu_w.oRvMvAQp1bWfx8KCJKNohg"],
    )

    name: str | None = Field(
        None,
        title="Full name of user",
        examples=["Mobu Test User"],
        exclude=True,
    )
