"""GitHub app integration models.
"""
from pydantic import BaseModel, Field, field_validator

__all__ = [
    "GitHubConfig",
]


class GitHubConfig(BaseModel):
    """Config for the GitHub CI app funcionality."""

    accepted_github_orgs: list[str] = Field(
        [],
        title="GitHub organizations to accept webhook requests from.",
        description=(
            "Any webhook payload request from a repo in an organization not in"
            " this list will get a 403 response."
        ),
    )
