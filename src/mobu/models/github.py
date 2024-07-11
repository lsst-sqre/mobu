"""GitHub app integration models.

Some of these could probably make their way back into Safir.
"""

import safir.github.models
import safir.github.webhooks
from pydantic import Field

__all__ = [
    "GitHubCheckSuiteEventModel",
    "GitHubCheckSuiteModel",
]


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
