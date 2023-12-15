"""Manage Gafaelfawr users and tokens."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

from httpx import AsyncClient, HTTPError
from pydantic import BaseModel, Field, ValidationError
from safir.datetime import current_datetime
from structlog.stdlib import BoundLogger

from ..config import config
from ..constants import TOKEN_LIFETIME, USERNAME_REGEX
from ..exceptions import GafaelfawrParseError, GafaelfawrWebError
from ..models.user import AuthenticatedUser, User

__all__ = ["GafaelfawrStorage"]


class _TokenType(Enum):
    """The class of token.

    This is copied from Gafaelfawr and should be replaced with using the
    Gafaelfawr models directly once they're available.
    """

    session = "session"
    user = "user"
    notebook = "notebook"
    internal = "internal"
    service = "service"


class _AdminTokenRequest(BaseModel):
    """Request by a Gafaelfawr token administrator to create a token.

    This is copied from Gafaelfawr and should be replaced with using the
    Gafaelfawr models directly once they're available.
    """

    username: str = Field(
        ..., min_length=1, max_length=64, pattern=USERNAME_REGEX
    )
    token_type: _TokenType = Field(...)
    scopes: list[str] = Field([])
    expires: datetime | None = Field(None)
    name: str | None = Field(None, min_length=1)
    uid: int | None = Field(None, ge=1)
    gid: int | None = Field(None, ge=1)


class _NewToken(BaseModel):
    """Response to a token creation request.

    This is copied from Gafaelfawr and should be replaced with using the
    Gafaelfawr models directly once they're available.
    """

    token: str = Field(...)


class GafaelfawrStorage:
    """Manage users and authentication tokens.

    mobu uses bot users to run its tests. Those users may be pre-existing or
    manufactured on the fly by mobu. Either way, mobu creates new service
    tokens for the configured users, and then provides those usernames and
    tokens to monkeys to use for executing their business.

    This class handles the call to Gafaelfawr to create the service token.

    Parameters
    ----------
    http_client
        Shared HTTP client.
    logger
        Logger to use.
    """

    def __init__(self, http_client: AsyncClient, logger: BoundLogger) -> None:
        self._client = http_client
        self._logger = logger

        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        base_url = str(config.environment_url).rstrip("/")
        self._token_url = base_url + "/auth/api/v1/tokens"

    async def create_service_token(
        self, user: User, scopes: list[str]
    ) -> AuthenticatedUser:
        """Create a service token for a user.

        Parameters
        ----------
        user
            Metadata for the user. If ``uid`` or ``gid`` are set for the user,
            they will be stored with the token and override Gafaelfawr's
            normal user metadata source.
        scopes
            Scopes the requested token should have.

        Returns
        -------
        AuthenticatedUser
            Authenticated user with their metadata, scopes, and token.

        Raises
        ------
        GafaelfawrParseError
            Raised if the input or output data for Gafaelfawr's token call
            could not be parsed.
        GafaelfawrWebError
            Raised if an HTTP protocol error occurred talking to Gafaelfawr.
        """
        request = _AdminTokenRequest(
            username=user.username,
            token_type=_TokenType.service,
            scopes=scopes,
            expires=current_datetime() + TOKEN_LIFETIME,
            name="Mobu Test User",
            uid=user.uidnumber,
            gid=user.gidnumber or user.uidnumber,
        )
        try:
            # The awkward JSON generation ensures that datetime fields are
            # properly serialized using the model rather than left as datetime
            # objects, which httpx will not understand. Pydantic v2 will offer
            # a better way to do this.
            r = await self._client.post(
                self._token_url,
                headers={"Authorization": f"Bearer {config.gafaelfawr_token}"},
                json=json.loads(request.model_dump_json(exclude_none=True)),
            )
            r.raise_for_status()
            token = _NewToken.model_validate(r.json())
            return AuthenticatedUser(
                username=user.username,
                uidnumber=request.uid,
                gidnumber=request.gid,
                token=token.token,
                scopes=scopes,
            )
        except HTTPError as e:
            raise GafaelfawrWebError.from_exception(e, user.username) from e
        except ValidationError as e:
            raise GafaelfawrParseError.from_exception(e, user.username) from e
