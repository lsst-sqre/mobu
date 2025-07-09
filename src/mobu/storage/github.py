"""Tools for interacting with the  GitHub REST API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from gidgethub.httpx import GitHubAPI
from pydantic import (
    AwareDatetime,
    Base64Str,
    BaseModel,
    Field,
    field_serializer,
)
from safir.github import GitHubAppClientFactory
from safir.github.models import GitHubCheckRunConclusion, GitHubCheckRunStatus

__all__ = ["CheckRun", "GitHubStorage"]


class _CheckRunRequestOutput(BaseModel):
    title: str | None = Field(None)
    summary: str | None = Field(None)
    text: str | None = Field(None)


class _CheckRunRequest(BaseModel):
    name: str | None = Field(None)
    head_sha: str = Field()
    status: GitHubCheckRunStatus | None = Field(None)
    conclusion: GitHubCheckRunConclusion | None = Field(None)
    started_at: AwareDatetime | None = Field(None)
    completed_at: AwareDatetime | None = Field(None)
    output: _CheckRunRequestOutput | None = Field(None)

    @field_serializer("started_at", "completed_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        if dt is not None:
            return dt.astimezone(UTC).isoformat()
        return None


class _CheckRunResponse(BaseModel):
    id: int = Field()


class _FileStatus(StrEnum):
    added = "added"
    removed = "removed"
    modified = "modified"
    renamed = "renamed"
    copied = "copied"
    changed = "changed"
    unchanged = "unchanged"


class _PullRequestFileResponse(BaseModel):
    filename: Path = Field()
    status: _FileStatus = Field()


class _FileContentsResponse(BaseModel):
    content: Base64Str = Field()


class GitHubStorage:
    """Tools to interact with the GitHub API.

    All interactions are scoped to a paricular repo and ref.

    Parameters
    ----------
    client
        An auth'd GitHub API client.
    repo_owner
        A GitHub organization.
    repo_name
        A GitHub repo.
    ref
        A Git ref.
    """

    def __init__(
        self,
        client: GitHubAPI,
        repo_owner: str,
        repo_name: str,
        ref: str,
        pull_number: int,
    ) -> None:
        self.client = client
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.ref = ref
        self._pull_number = pull_number
        self.commit_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/commit/{self.ref}"
        self._api_path = f"/repos/{repo_owner}/{repo_name}"

    @classmethod
    async def create(
        cls,
        factory: GitHubAppClientFactory,
        installation_id: int,
        repo_owner: str,
        repo_name: str,
        ref: str,
        pull_number: int,
    ) -> Self:
        """Create an auth'd GitHub client and construct an instance.

        Parameters
        ----------
        factory
            A GitHub client factory with credentials.
        installation_id
            The ID of an installed GitHub app.
        repo_owner
            A GitHub organization.
        repo_name
            A GitHub repo.
        ref
            A GitHub ref.
        pull_number
            The number that identifies a pull request.
        """
        client = await factory.create_installation_client(
            installation_id=installation_id,
        )
        return cls(
            client=client,
            repo_name=repo_name,
            repo_owner=repo_owner,
            ref=ref,
            pull_number=pull_number,
        )

    async def get_pr_files(self) -> list[Path]:
        """Get a list of all changed or added files in the pull request.

        Returns
        -------
        list[Path]
            List of paths relative to the repo root.
        """
        path = f"{self._api_path}/pulls/{self._pull_number}/files"
        files = [
            _PullRequestFileResponse.model_validate(info)
            async for info in self.client.getiter(path)
        ]
        return [
            file.filename
            for file in files
            if file.status
            in (
                _FileStatus.modified,
                _FileStatus.changed,
                _FileStatus.added,
            )
        ]

    async def create_check_run(
        self,
        name: str,
        summary: str,
        details: str | None = None,
    ) -> CheckRun:
        """Create a check run and return an object to manage it.

        Parameters
        ----------
        name
            The name of the checkrun. This will also be output title.
        summary
            The output summary.
        details
            The output details

        Returns
        -------
        CheckRun
            An object to manage GitHub check run status.
        """
        path = f"/repos/{self.repo_owner}/{self.repo_name}/check-runs"
        data = _CheckRunRequest(
            head_sha=self.ref,
            name=name,
            status=GitHubCheckRunStatus.queued,
            started_at=datetime.now(UTC),
            output=_CheckRunRequestOutput(
                title=name,
                summary=summary,
                text=details,
            ),
        ).model_dump(exclude_unset=True, exclude_none=True)

        res = await self.client.post(path, data=data)
        check_run = _CheckRunResponse.model_validate(res)

        return CheckRun(
            github_storage=self,
            id=check_run.id,
            name=name,
            summary=summary,
            details=details,
        )


class CheckRun:
    """Manage GitHub check runs via the GitHub API.

    Parameters
    ----------
    github_storage
        To interact with the github api
    id
        The GitHub API check run ID.
    name
        The name of the checkrun. This will also be output title.
    summary
        The output summary.
    details
        The output details
    """

    def __init__(
        self,
        github_storage: GitHubStorage,
        id: int,
        name: str,
        summary: str,
        details: str | None = None,
    ) -> None:
        self._client = github_storage.client
        self._ref = github_storage.ref
        self._name = name
        self._summary = summary
        self._text = details
        self._api_path = (
            f"/repos/{github_storage.repo_owner}/"
            f"{github_storage.repo_name}/check-runs/{id}"
        )

    async def fail(self, error: str) -> None:
        """Conclude a GitHub check run as a failure.

        Parameters
        ----------
        error
            The error that occurred.
        """
        await self._update(
            conclusion=GitHubCheckRunConclusion.failure,
            text=error,
        )

    async def succeed(self, details: str | None = None) -> None:
        """Conclude a GitHub check run as a success.

        Parameters
        ----------
        details
            Output details to display.
        """
        await self._update(
            conclusion=GitHubCheckRunConclusion.success,
            text=details,
        )

    async def start(
        self,
        summary: str | None = None,
        details: str | None = None,
    ) -> None:
        """Update a GitHub check run to: in progress.

        Parameters
        ----------
        summary
            The output summary to display.
        details
            Output details to display.
        """
        await self._update(
            status=GitHubCheckRunStatus.in_progress,
            summary=summary,
            text=details,
        )

    async def _update(
        self,
        status: GitHubCheckRunStatus | None = None,
        conclusion: GitHubCheckRunConclusion | None = None,
        summary: str | None = None,
        text: str | None = None,
    ) -> None:
        """Update a check run, update internal state if necessary."""
        self._summary = summary or self._summary
        self._text = text or self._text

        now = datetime.now(UTC)
        request = _CheckRunRequest(
            head_sha=self._ref,
            status=status,
            conclusion=conclusion,
            completed_at=now if conclusion is not None else None,
            output=_CheckRunRequestOutput(
                title=self._name,
                summary=self._summary,
                text=self._text,
            ),
        )
        data = request.model_dump(exclude_unset=True, exclude_none=True)
        await self._client.patch(
            self._api_path,
            data=data,
        )
