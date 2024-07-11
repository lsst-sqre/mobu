"""Config for GitHub application integrations."""

from textwrap import dedent

from pydantic import Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models.user import User


class GitHubCiAppConfig(BaseSettings):
    """Configuration for GitHub CI app functionality if it is enabled."""

    model_config = SettingsConfigDict(
        alias_generator=to_camel, extra="forbid", populate_by_name=True
    )

    id: int = Field(
        ...,
        title="Github CI app id",
        description=(
            "Found on the GitHub app's settings page (NOT the installation"
            " configuration page). For example:"
            " https://github.com/organizations/lsst-sqre/settings/apps/mobu-ci-data-dev-lsst-cloud"
        ),
        validation_alias="MOBU_GITHUB_CI_APP_ID",
        examples=[123456],
    )

    private_key: str = Field(
        ...,
        title="Github CI app private key",
        description=(
            "Generated when the GitHub app was set up. This should NOT be"
            " base64 enocded, and will contain newlines. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
        validation_alias="MOBU_GITHUB_CI_APP_PRIVATE_KEY",
        examples=[
            dedent("""
            -----BEGIN RSA PRIVATE KEY-----
            abc123MeowMeow456abc123MeowMeow456abc123MeowMeow456abc123MeowMeo
            abc123MeowMeow456abc123MeowMeow456abc123MeowMeow456abc123MeowMeo
            abc123MeowMeow456abc123MeowMeow456abc123MeowMeow456abc123MeowMeo
            etc, etc
            -----END RSA PRIVATE KEY-----
        """)
        ],
    )

    webhook_secret: str = Field(
        ...,
        title="Github CI app webhook secret",
        description=(
            "Generated when the GitHub app was set up. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
        validation_alias="MOBU_GITHUB_CI_APP_WEBHOOK_SECRET",
    )

    users: list[User] = Field(
        ...,
        title="Environment users for CI jobs to run as.",
        description=(
            "Must be prefixed with 'bot-', like all mobu users. In "
            " environments without Firestore, users have to be provisioned"
            " by environment admins, and their usernames, uids, and guids must"
            " be specified here. In environments with firestore, only "
            " usernames need to be specified, but you still need to explicitly"
            " specify as many users as needed to get the amount of concurrency"
            " that you want."
        ),
    )

    scopes: list[str] = Field(
        ...,
        title="Gafaelfawr Scopes",
        description=(
            "A list of Gafaelfawr scopes that will be granted to the"
            " user when running notebooks for a GitHub CI app check."
        ),
    )

    accepted_github_orgs: list[str] = Field(
        [],
        title="Allowed GitHub organizations.",
        description=(
            "Any webhook payload request from a repo in an organization not in"
            " this list will get a 403 response."
        ),
    )


class GitHubRefreshAppConfig(BaseSettings):
    """Configuration for GitHub refresh app functionality."""

    model_config = SettingsConfigDict(
        alias_generator=to_camel, extra="forbid", populate_by_name=True
    )

    webhook_secret: str = Field(
        ...,
        title="Github refresh app webhook secret",
        description=(
            "Generated when the GitHub app was set up. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
        validation_alias="MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET",
    )

    accepted_github_orgs: list[str] = Field(
        [],
        title="Allowed GitHub organizations.",
        description=(
            "Any webhook payload request from a repo in an organization not in"
            " this list will get a 403 response."
        ),
    )
