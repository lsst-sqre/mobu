"""Exceptions for mobu."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Self

from fastapi import status
from pydantic import ValidationError
from safir.datetime import format_datetime_for_logging
from safir.fastapi import ClientRequestError
from safir.models import ErrorLocation
from safir.slack.blockkit import (
    SlackBaseBlock,
    SlackBaseField,
    SlackCodeBlock,
    SlackException,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
    SlackWebException,
)
from websockets.exceptions import InvalidStatus, WebSocketException

_ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
"""Regex that matches ANSI escape sequences."""

__all__ = [
    "CachemachineError",
    "CodeExecutionError",
    "FlockNotFoundError",
    "GafaelfawrParseError",
    "GafaelfawrWebError",
    "JupyterTimeoutError",
    "JupyterWebError",
    "MobuSlackException",
    "MobuSlackWebException",
    "MonkeyNotFoundError",
    "TAPClientError",
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


class MobuSlackException(SlackException):
    """Represents an exception that can be reported to Slack.

    This adds some additional fields to `~safir.slack.blockkit.SlackException`
    but is otherwise equivalent. It is intended to be subclassed. Subclasses
    must override the `to_slack` method.

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
    started_at
        When the operation that ended in an exception started.
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
        super().__init__(msg, user, failed_at=failed_at)
        self.started_at = started_at
        self.monkey: str | None = None
        self.event: str | None = None
        self.annotations: dict[str, str] = {}

    def to_slack(self) -> SlackMessage:
        """Format the error as a Slack Block Kit message.

        This is the generic version that only reports the text of the
        exception and common fields. Most classes will want to override it.

        Returns
        -------
        SlackMessage
            Formatted Slack message.
        """
        return SlackMessage(
            message=str(self),
            blocks=self.common_blocks(),
            fields=self.common_fields(),
        )

    def common_blocks(self) -> list[SlackBaseBlock]:
        """Return common blocks to put in any alert.

        Returns
        -------
        list of SlackBaseBlock
            Common blocks to add to the Slack message.
        """
        blocks: list[SlackBaseBlock] = []
        if self.annotations.get("node"):
            node = self.annotations["node"]
            blocks.append(SlackTextBlock(heading="Node", text=node))
        if self.annotations.get("notebook"):
            notebook = self.annotations["notebook"]
            if self.annotations.get("cell"):
                cell = self.annotations["cell"]
                text = f"`{notebook}` cell {cell}"
                blocks.append(SlackTextBlock(heading="Cell", text=text))
            else:
                block = SlackTextBlock(heading="Notebook", text=notebook)
                blocks.append(block)
        elif self.annotations.get("cell"):
            cell = self.annotations["cell"]
            blocks.append(SlackTextBlock(heading="Cell", text=cell))
        return blocks

    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        failed_at = format_datetime_for_logging(self.failed_at)
        fields: list[SlackBaseField] = [
            SlackTextField(heading="Failed at", text=failed_at),
            SlackTextField(heading="Exception type", text=type(self).__name__),
        ]
        if self.started_at:
            started_at = format_datetime_for_logging(self.started_at)
            field = SlackTextField(heading="Started at", text=started_at)
            fields.insert(0, field)
        if self.monkey:
            fields.append(SlackTextField(heading="Monkey", text=self.monkey))
        if self.user:
            fields.append(SlackTextField(heading="User", text=self.user))
        if self.event:
            fields.append(SlackTextField(heading="Event", text=self.event))
        if self.annotations.get("image"):
            image = self.annotations["image"]
            fields.append(SlackTextField(heading="Image", text=image))
        return fields


class MobuSlackWebException(SlackWebException, MobuSlackException):
    """Represents an exception that can be reported to Slack.

    Similar to `MobuSlackException`, this adds some additional fields to
    `~safir.slack.blockkit.SlackWebException` but is otherwise equivalent. It
    is intended to be subclassed. Subclasses may want to override the
    `to_slack` method.
    """


class NotebookRepositoryError(MobuSlackException):
    """The repository containing notebooks to run is not valid."""


class CachemachineError(MobuSlackException):
    """Failed to obtain a valid image list from cachemachine."""

    def __init__(self, msg: str) -> None:
        super().__init__(f"Cachemachine error: {msg}")


class CodeExecutionError(MobuSlackException):
    """Error generated by code execution in a notebook on JupyterLab."""

    def __init__(
        self,
        *,
        user: str,
        code: str | None = None,
        code_type: str = "code",
        error: str | None = None,
        status: str | None = None,
    ) -> None:
        super().__init__("Code execution failed", user)
        self.code = code
        self.code_type = code_type
        self.error = error
        self.status = status

    def __str__(self) -> str:
        if self.annotations.get("notebook"):
            notebook = self.annotations["notebook"]
            if self.annotations.get("cell"):
                cell = self.annotations["cell"]
                msg = f"{self.user}: cell {cell} of notebook {notebook} failed"
            else:
                msg = f"{self.user}: cell of notebook {notebook} failed"
            if self.status:
                msg += f" (status: {self.status})"
            if self.code:
                msg += f"\nCode: {self.code}"
        elif self.code:
            msg = f"{self.user}: running {self.code_type} '{self.code}' failed"
        else:
            msg = f"{self.user}: running {self.code_type} failed"
        if self.error:
            msg += f"\nError: {_remove_ansi_escapes(self.error)}"
        return msg

    def to_slack(self) -> SlackMessage:
        """Format the error as a Slack Block Kit message."""
        if self.annotations.get("notebook"):
            notebook = self.annotations["notebook"]
            intro = f"Error while running `{notebook}`"
        else:
            intro = f"Error while running {self.code_type}"
        if self.status:
            intro += f" (status: {self.status})"

        attachments: list[SlackBaseBlock] = []
        if self.error:
            error = _remove_ansi_escapes(self.error)
            attachment = SlackCodeBlock(heading="Error", code=error)
            attachments.append(attachment)
        if self.code:
            attachment = SlackCodeBlock(
                heading="Code executed", code=self.code
            )
            attachments.append(attachment)

        return SlackMessage(
            message=intro,
            fields=self.common_fields(),
            blocks=self.common_blocks(),
            attachments=attachments,
        )


class JupyterSpawnError(MobuSlackException):
    """The Jupyter Lab pod failed to spawn."""

    @classmethod
    def from_exception(cls, log: str, exc: Exception, user: str) -> Self:
        """Convert from an arbitrary exception to a spawn error.

        Parameters
        ----------
        log
            Log of the spawn to this point.
        exc
            Exception that terminated the spawn attempt.
        user
            Username of the user spawning the lab.

        Returns
        -------
        JupyterSpawnError
            Converted exception.
        """
        if str(exc):
            return cls(log, user, f"{type(exc).__name__}: {exc!s}")
        else:
            return cls(log, user, type(exc).__name__)

    def __init__(
        self, log: str, user: str, message: str | None = None
    ) -> None:
        if message:
            message = f"Spawning lab failed: {message}"
        else:
            message = "Spawning lab failed"
        super().__init__(message, user)
        self.log = log

    def to_slack(self) -> SlackMessage:
        """Format the error as a Slack Block Kit message."""
        message = super().to_slack()
        if self.log:
            block = SlackTextBlock(heading="Log", text=self.log)
            message.blocks.append(block)
        return message


class JupyterTimeoutError(MobuSlackException):
    """Timed out waiting for the lab to spawn."""

    def __init__(
        self,
        msg: str,
        user: str,
        log: str | None = None,
        *,
        started_at: datetime | None = None,
    ) -> None:
        super().__init__(msg, user, started_at=started_at)
        self.log = log

    def to_slack(self) -> SlackMessage:
        """Format the error as a Slack Block Kit message."""
        message = super().to_slack()
        if self.log:
            message.blocks.append(SlackTextBlock(heading="Log", text=self.log))
        return message


class JupyterWebError(MobuSlackWebException):
    """An error occurred when talking to JupyterHub or a Jupyter lab."""


class JupyterWebSocketError(MobuSlackException):
    """An error occurred talking to the Jupyter lab WebSocket."""

    @classmethod
    def from_exception(cls, exc: WebSocketException, user: str) -> Self:
        """Convert from a `~websockets.exceptions.WebSocketException`.

        Parameters
        ----------
        exc
            Underlying exception.
        user
            User the monkey is running as.

        Returns
        -------
        JupyterWebSocketError
            Newly-created exception.
        """
        if str(exc):
            error = f"{type(exc).__name__}: {exc!s}"
        else:
            error = type(exc).__name__
        if isinstance(exc, InvalidStatus):
            status = exc.response.status_code
            return cls(
                f"Lab WebSocket unexpectedly closed: {error}",
                user=user,
                status=status,
                body=exc.response.body,
            )
        else:
            return cls(f"Error talking to lab WebSocket: {error}", user=user)

    def __init__(
        self,
        msg: str,
        *,
        user: str,
        code: int | None = None,
        reason: str | None = None,
        status: int | None = None,
        body: bytes | None = None,
    ) -> None:
        super().__init__(msg, user)
        self.code = code
        self.reason = reason
        self.status = status
        self.body = body.decode() if body else None

    def to_slack(self) -> SlackMessage:
        """Format this exception as a Slack notification.

        Returns
        -------
        SlackMessage
            Formatted message.
        """
        message = super().to_slack()

        if self.reason:
            reason = self.reason
            if self.code:
                reason = f"{self.reason} ({self.code})"
            else:
                reason = self.reason
            field = SlackTextField(heading="Reason", text=reason)
            message.fields.append(field)
        elif self.code:
            field = SlackTextField(heading="Code", text=str(self.code))
            message.fields.append(field)

        if self.body:
            block = SlackTextBlock(heading="Body", text=self.body)
            message.blocks.append(block)

        return message


class TAPClientError(MobuSlackException):
    """Creating a TAP client failed."""

    def __init__(self, exc: Exception, *, user: str) -> None:
        if str(exc):
            error = f"{type(exc).__name__}: {exc!s}"
        else:
            error = type(exc).__name__
        msg = f"Unable to create TAP client: {error}"
        super().__init__(msg, user)
