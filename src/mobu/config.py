"""Configuration definition."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Literal, Self

import yaml
from pydantic import AliasChoices, Field, HttpUrl, SecretStr
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict
from safir.logging import LogLevel, Profile
from safir.metrics import MetricsConfiguration, metrics_configuration_factory
from safir.pydantic import HumanTimedelta

from mobu.models.flock import FlockConfig

from .models.user import User

__all__ = [
    "Config",
    "GitHubCiAppConfig",
    "GitHubRefreshAppConfig",
]


class GitHubCiAppConfig(BaseSettings):
    """Configuration for GitHub CI app functionality if it is enabled."""

    model_config = SettingsConfigDict(
        alias_generator=to_camel, extra="forbid", validate_by_name=True
    )

    id: int = Field(
        ...,
        title="Github CI app id",
        description=(
            "Found on the GitHub app's settings page (NOT the installation"
            " configuration page). For example:"
            " https://github.com/organizations/lsst-sqre/settings/apps/mobu-ci-data-dev-lsst-cloud"
        ),
        examples=[123456],
        validation_alias=AliasChoices("MOBU_GITHUB_CI_APP_ID", "id"),
    )

    private_key: str = Field(
        ...,
        title="Github CI app private key",
        description=(
            "Generated when the GitHub app was set up. This should NOT be"
            " base64 enocded, and will contain newlines. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
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
        validation_alias=AliasChoices(
            "MOBU_GITHUB_CI_APP_PRIVATE_KEY", "privateKey"
        ),
    )

    webhook_secret: str = Field(
        ...,
        title="Github CI app webhook secret",
        description=(
            "Generated when the GitHub app was set up. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
        validation_alias=AliasChoices(
            "MOBU_GITHUB_CI_APP_WEBHOOK_SECRET", "webhookSecret"
        ),
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
        alias_generator=to_camel, extra="forbid", validate_by_name=True
    )

    webhook_secret: str = Field(
        ...,
        title="Github refresh app webhook secret",
        description=(
            "Generated when the GitHub app was set up. You can find this"
            " in 1Password; check the Phalanx mobu values for more details."
        ),
        validation_alias=AliasChoices(
            "MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET", "webhookSecret"
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


class Config(BaseSettings):
    """Configuration for mobu."""

    model_config = SettingsConfigDict(
        alias_generator=to_camel, extra="forbid", validate_by_name=True
    )

    slack_alerts: bool = Field(
        False,
        title="Enable Slack alerts",
        description=(
            "Whether to enable Slack alerts. If true, ``alert_hook`` must"
            " also be set."
        ),
    )

    alert_hook: SecretStr | None = Field(
        None,
        title="Slack alert webhook URL",
        description="Slack incoming webhook to which to send alerts",
        examples=["https://slack.example.com/ADFAW1452DAF41/"],
        validation_alias=AliasChoices("MOBU_ALERT_HOOK", "alertHook"),
    )

    environment_url: HttpUrl | None = Field(
        None,
        title="Base URL of the Science Platform environment",
        description=(
            "Used to create URLs to other services, such as Gafaelfawr and"
            " JupyterHub. This is only optional to make writing the test"
            " suite easier. If it is not set to a valid URL, mobu will abort"
            " during startup."
        ),
        examples=["https://data.example.org/"],
        validation_alias=AliasChoices(
            "MOBU_ENVIRONMENT_URL", "environmentUrl"
        ),
    )

    sentry_dsn: str | None = Field(
        None,
        title="Sentry DSN",
        description="The Sentry DSN: https://docs.sentry.io/platforms/python/#configure",
        examples=[
            "https://foo@bar.ingest.us.sentry.io/123456",
        ],
        validation_alias=AliasChoices("MOBU_SENTRY_DSN", "mobuSentryDsn"),
    )

    sentry_traces_sample_config: float | Literal["errors"] = Field(
        0,
        title="Sentry traces sample config",
        description=(
            "Set the Sentry sampling strategy for traces. If this is a float,"
            " it will be passed as the traces_sample_rate: https://docs.sentry.io/platforms/python/configuration/sampling/#configuring-the-transaction-sample-rate"
            ' If this is set to "errors", then all transactions during which'
            " an error occurred will be sent."
        ),
        examples=[0, 0.5, "errors"],
        validation_alias=AliasChoices(
            "MOBU_SENTRY_TRACES_SAMPLE_CONFIG", "sentryTracesSampleConfig"
        ),
    )

    sentry_environment: str = Field(
        ...,
        title="Sentry environment",
        description=(
            "The Sentry environment: https://docs.sentry.io/concepts/key-terms/environments/"
        ),
        validation_alias=AliasChoices(
            "MOBU_SENTRY_ENVIRONMENT", "sentryEnvironment"
        ),
    )

    gafaelfawr_token: str | None = Field(
        None,
        title="Gafaelfawr admin token",
        description=(
            "This token is used to make an admin API call to Gafaelfawr to"
            " get a token for the user. This is only optional to make writing"
            " tests easier. mobu will abort during startup if it is not set."
        ),
        examples=["gt-vilSCi1ifK_MyuaQgMD2dQ.d6SIJhowv5Hs3GvujOyUig"],
        validation_alias=AliasChoices(
            "MOBU_GAFAELFAWR_TOKEN", "gafaelfawrToken"
        ),
    )

    gafaelfawr_timeout: HumanTimedelta | None = Field(
        None,
        title="Gafaelfawr client timeout",
        description=(
            "The time to set for all httpx timeouts. If this None, then the"
            " timeouts will be set to the default timeouts from the Safir"
            " http client dependency."
        ),
        examples=["3m", 45, "45", "1.4s"],
    )

    available_services: set[str] = Field(
        set(),
        title="Available platform services",
        description=(
            "Names of services available in the current environment. For now,"
            " this list is manually maintained in the mobu config in Phalanx."
            " When we have a service discovery mechanism in place, it should"
            " be used here."
        ),
        examples=[{"tap", "ssotap", "butler"}],
    )

    name: str = Field(
        "mobu",
        title="Name of application",
        description="Doubles as the root HTTP endpoint path.",
    )

    autostart: list[FlockConfig] = Field(
        default=[],
        title="Autostart config",
        description=(
            "Configuration of flocks of monkeys that will run businesses"
            " repeatedly as long as Mobu is running."
        ),
    )

    path_prefix: str = Field(
        "/mobu",
        title="URL prefix for application API",
    )

    profile: Profile = Field(
        Profile.development,
        title="Application logging profile",
    )

    log_level: LogLevel = Field(
        LogLevel.INFO,
        title="Log level of the application's logger",
    )

    log_monkeys_to_file: bool = Field(
        True,
        title="Log monkey messages to a file",
        description=(
            "Log monkey messages to a file instead of doing whatever the"
            " normal global logger does"
        ),
    )

    replica_count: int = Field(
        ...,
        title="Replica count",
        description=(
            "The number of instances of that this StatefulSet will be running."
            " If this is more than one, then only user_spec user definitions"
            " will be allowed."
        ),
        validation_alias=AliasChoices("MOBU_REPLICA_COUNT", "replicaCount"),
    )

    replica_index: int = Field(
        ...,
        title="Replica index",
        description=(
            "Mobu is deployed as a StatefulSet. Every replica is assigned an"
            " integer index, starting with 0 and counting up. This value is"
            " this instance's assigned index."
        ),
        validation_alias=AliasChoices("MOBU_REPLICA_INDEX", "replicaIndex"),
    )

    metrics: MetricsConfiguration = Field(
        default_factory=metrics_configuration_factory,
        title="Metrics configuration",
    )

    github_ci_app: GitHubCiAppConfig | None = Field(
        None,
        title="GitHub CI app config",
        description=("Configuration for GitHub CI app functionality"),
    )

    github_refresh_app: GitHubRefreshAppConfig | None = Field(
        None,
        title="GitHub refresh app config",
        description=("Configuration for GitHub refresh app functionality"),
    )

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Construct a Configuration object from a configuration file.

        Parameters
        ----------
        path
            Path to the configuration file in YAML.

        Returns
        -------
        Config
            The corresponding `Configuration` object.
        """
        with path.open("r") as f:
            return cls.model_validate(yaml.safe_load(f))
