"""Manage Gafaelfawr users and tokens."""

from __future__ import annotations

from rubin.gafaelfawr import GafaelfawrClient, GafaelfawrGroup
from safir.datetime import current_datetime
from structlog.stdlib import BoundLogger

from ..config import Config
from ..constants import TOKEN_LIFETIME
from ..models.user import AuthenticatedUser, User

__all__ = ["GafaelfawrStorage"]


class GafaelfawrStorage:
    """Manage users and authentication tokens.

    mobu uses bot users to run its tests. Those users may be pre-existing or
    manufactured on the fly by mobu. Either way, mobu creates new service
    tokens for the configured users, and then provides those usernames and
    tokens to monkeys to use for executing their business.

    This class handles the call to Gafaelfawr to create the service token.

    Parameters
    ----------
    config
        mobu configuration.
    gafaelfawr_client
        Shared Gafaelfawr client.
    logger
        Logger to use.
    """

    def __init__(
        self,
        config: Config,
        gafaelfawr_client: GafaelfawrClient,
        logger: BoundLogger,
    ) -> None:
        self._config = config
        self._gafaelfawr = gafaelfawr_client
        self._logger = logger

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
        rubin.gafaelfawr.GafaelfawrError
            Raised if the request to Gafaelfawr failed.
        """
        token = await self._gafaelfawr.create_service_token(
            self._config.gafaelfawr_token,
            user.username,
            scopes=scopes,
            expires=current_datetime() + TOKEN_LIFETIME,
            name="Mobu Test User",
            uid=user.uidnumber,
            gid=user.gidnumber or user.uidnumber,
            groups=[
                GafaelfawrGroup(name=g.name, id=g.id) for g in user.groups
            ],
        )
        return AuthenticatedUser(
            token=token,
            scopes=scopes,
            username=user.username,
            uidnumber=user.uidnumber,
            gidnumber=user.gidnumber or user.uidnumber,
            groups=user.groups,
        )
