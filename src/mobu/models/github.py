"""GitHub app integration models.

Some of these could probably make their way back into Safir.
"""

import safir.github.models
import safir.github.webhooks
from pydantic import BaseModel, Field, field_validator

from .user import User

__all__ = [
    "GitHubCheckSuiteEventModel",
    "GitHubCheckSuiteModel",
    "GitHubConfig",
]


class GitHubConfig(BaseModel):
    """Config for the GitHub CI app funcionality."""

    users: list[User] = Field(
        [],
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
    accepted_github_orgs: list[str] = Field(
        [],
        title="GitHub organizations to accept webhook requests from.",
        description=(
            "Any webhook payload request from a repo in an organization not in"
            " this list will get a 403 response."
        ),
    )

    @field_validator("users")
    @classmethod
    def check_bot_user(cls, v: list[User]) -> list[User]:
        bad = [u.username for u in v if not u.username.startswith("bot-")]
        if any(bad):
            raise ValueError(
                f"All usernames must start with 'bot-'. These don't: {bad}"
            )
        return v


class GitHubCheckSuiteModel(
    safir.github.models.GitHubCheckSuiteModel,
):
    """Adding ``pull_requests`` field to the existing check suite model."""

    pull_requests: list[safir.github.models.GitHubCheckRunPrInfoModel] = (
        Field()
    )


class GitHubCheckSuiteEventModel(
    safir.github.webhooks.GitHubCheckSuiteEventModel,
):
    """Overriding ``check_suite`` to add ``pull_requests``."""

    check_suite: GitHubCheckSuiteModel = Field()
