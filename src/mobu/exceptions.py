"""Exceptions for mobu."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Self

from fastapi import status
from pydantic import ValidationError
from rubin.nublado.client.exceptions import (
    NubladoClientSlackException,
    NubladoClientSlackWebException,
)
from safir.fastapi import ClientRequestError
from safir.models import ErrorLocation
from safir.slack.blockkit import (
    SlackBaseField,
    SlackCodeBlock,
    SlackException,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
    SlackWebException,
)

_ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
"""Regex that matches ANSI escape sequences."""

__all__ = [
    "ComparisonError",
    "FlockNotFoundError",
    "GafaelfawrParseError",
    "GafaelfawrWebError",
    "GitHubFileNotFoundError",
    "MobuSlackException",
    "MobuSlackWebException",
    "MonkeyNotFoundError",
    "TAPClientError",
    "SubprocessError",
]


def _remove_ansi_escapes(string: str) -> str:
    """Remove ANSI escape sequences from a string.

    Jupyter labs like to format error messages with lots of ANSI escape
    sequences, and Slack doesn't like that in messages (nor do humans want to
    see them). Strip them out.

    Based on `this StackOverflow answer
    <https://stackoverflow.com/questions/14693701/>`__.

    Parameters
    ----------
    string
        String to strip ANSI escapes from.

    Returns
    -------
    str
        Sanitized string.
    """
    return _ANSI_REGEX.sub("", string)


class GafaelfawrParseError(SlackException):
    """Unable to parse the reply from Gafaelfawr.

    Parameters
    ----------
    message
        Summary error message.
    error
        Detailed error message, possibly multi-line.
    user
        Username of the user involved.
    """

    @classmethod
    def from_exception(
        cls, exc: ValidationError, user: str | None = None
    ) -> Self:
        """Create an exception from a Pydantic parse failure.

        Parameters
        ----------
        exc
            Pydantic exception.
        user
            Username of the user involved.

        Returns
        -------
        GafaelfawrParseError
            Constructed exception.
        """
        error = f"{type(exc).__name__}: {exc!s}"
        return cls("Unable to parse reply from Gafalefawr", error, user)

    def __init__(
        self, message: str, error: str, user: str | None = None
    ) -> None:
        super().__init__(message, user)
        self.error = error

    def to_slack(self) -> SlackMessage:
        """Convert to a Slack message for Slack alerting.

        Returns
        -------
        SlackMessage
            Slack message suitable for posting as an alert.
        """
        message = super().to_slack()
        block = SlackCodeBlock(heading="Error", code=self.error)
        message.blocks.append(block)
        return message


class GafaelfawrWebError(SlackWebException):
    """An API call to Gafaelfawr failed."""


class FlockNotFoundError(ClientRequestError):
    """The named flock was not found."""

    error = "flock_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, flock: str) -> None:
        self.flock = flock
        msg = f"Flock {flock} not found"
        super().__init__(msg, ErrorLocation.path, ["flock"])


class MonkeyNotFoundError(ClientRequestError):
    """The named monkey was not found."""

    error = "monkey_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, monkey: str) -> None:
        self.monkey = monkey
        msg = f"Monkey {monkey} not found"
        super().__init__(msg, ErrorLocation.path, ["monkey"])


class MobuSlackException(NubladoClientSlackException):
    """Represents an exception that can be reported to Slack.

    This adds some additional fields to
    `~rubin.nublado.client.NubladoClientSlackException` but is otherwise
    equivalent. It is intended to be subclassed. Subclasses should override
    the `to_slack` method.

    Parameters
    ----------
    msg
        Exception message.
    user
        User mobu was operating as when the exception happened.
    started_at
        When the operation started.
    failed_at
        When the operation failed (defaults to the current time).

    Attributes
    ----------
    monkey
        The running monkey in which the exception happened.
    event
        Name of the business event that provoked the exception.
    annotations
        Additional annotations for the running business.
    """

    def __init__(
        self,
        msg: str,
        user: str | None = None,
        *,
        started_at: datetime | None = None,
        failed_at: datetime | None = None,
    ) -> None:
        super().__init__(msg, user, started_at=started_at, failed_at=failed_at)
        self.monkey: str | None = None
        self.event: str | None = None
        self.annotations: dict[str, str] = {}

    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        if self.monkey:
            fields.append(SlackTextField(heading="Monkey", text=self.monkey))
        if self.event:
            fields.append(SlackTextField(heading="Event", text=self.event))
        return fields


class MobuSlackWebException(
    NubladoClientSlackWebException, MobuSlackException
):
    """Represents an exception that can be reported to Slack.

    Similar to `MobuSlackException`, this adds some additional fields to
    `~rubin.nublado.client.exceptions.NubladoClientSlackWebException` but is
    otherwise equivalent. It is intended to be subclassed. Subclasses may
    want to override the `to_slack` method.
    """


class NotebookRepositoryError(MobuSlackException):
    """The repository containing notebooks to run is not valid."""


class RepositoryConfigError(MobuSlackException):
    """The in-repo mobu.yaml config file is invalid."""

    def __init__(
        self,
        *,
        err: Exception,
        user: str,
        repo_url: str,
        repo_ref: str,
        config_file: Path,
    ) -> None:
        super().__init__(str(err), user)
        self.err = err
        self.user = user
        self.repo_url = repo_url
        self.repo_ref = repo_ref
        self.config_file = config_file

    def to_slack(self) -> SlackMessage:
        message = super().to_slack()
        message.blocks += [
            SlackTextBlock(heading="GitHub Repository", text=self.repo_url),
            SlackTextBlock(heading="Git Ref", text=self.repo_ref),
        ]
        message.attachments += [
            SlackCodeBlock(
                heading="Error",
                code=f"{type(self.err).__name__}: {self.err!s}",
            )
        ]
        message.message = f"Error parsing config file: {self.config_file}"
        return message


class GitHubFileNotFoundError(Exception):
    """Tried to retrieve contents for a non-existent file in a GitHub
    repo.
    """


class TAPClientError(MobuSlackException):
    """Creating a TAP client failed."""

    def __init__(self, exc: Exception, *, user: str) -> None:
        if str(exc):
            error = f"{type(exc).__name__}: {exc!s}"
        else:
            error = type(exc).__name__
        msg = f"Unable to create TAP client: {error}"
        super().__init__(msg, user)


class SubprocessError(MobuSlackException):
    """Running a subprocess failed."""

    def __init__(
        self,
        msg: str,
        *,
        user: str | None = None,
        returncode: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        super().__init__(msg, user)
        self.msg = msg
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.cwd = cwd
        self.env = env

    def __str__(self) -> str:
        return (
            f"{self.msg} with rc={self.returncode};"
            f" stdout='{self.stdout}'; stderr='{self.stderr}'"
            f" cwd='{self.cwd}'; env='{self.env}'"
        )

    def to_slack(self) -> SlackMessage:
        """Format this exception as a Slack notification.

        Returns
        -------
        SlackMessage
            Formatted message.
        """
        message = SlackMessage(
            message=self.msg,
            blocks=self.common_blocks(),
            fields=self.common_fields(),
        )

        field = SlackTextField(
            heading="Return Code", text=str(self.returncode)
        )
        message.fields.append(field)
        if self.cwd:
            message.fields.append(field)
            field = SlackTextField(heading="Directory", text=str(self.cwd))
        if self.stdout:
            block = SlackCodeBlock(heading="Stdout", code=self.stdout)
            message.blocks.append(block)
        if self.stderr:
            block = SlackCodeBlock(heading="Stderr", code=self.stderr)
            message.blocks.append(block)
        if self.env:
            block = SlackCodeBlock(
                heading="Environment",
                code=json.dumps(self.env, sort_keys=True, indent=4),
            )
            message.blocks.append(block)
        return message


class ComparisonError(MobuSlackException):
    """Comparing two strings failed."""

    def __init__(
        self,
        user: str | None = None,
        *,
        expected: str,
        received: str,
    ) -> None:
        super().__init__("Comparison failed", user)
        self.expected = expected
        self.received = received

    def __str__(self) -> str:
        return (
            f"Comparison failed: expected '{self.expected}', but"
            f" received '{self.received}'"
        )

    def to_slack(self) -> SlackMessage:
        """Format this exception as a Slack notification.

        Returns
        -------
        SlackMessage
            Formatted message.
        """
        message = super().to_slack()
        field = SlackTextField(heading="Expected", text=self.expected)
        message.fields.append(field)
        field = SlackTextField(heading="Received", text=self.received)
        message.fields.append(field)
        return message
