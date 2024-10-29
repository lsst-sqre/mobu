"""Exceptions for mobu."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Self, override

import rubin.nublado.client.exceptions as ne
from fastapi import status
from pydantic import ValidationError
from safir.fastapi import ClientRequestError
from safir.models import ErrorLocation
from safir.slack.blockkit import (
    SlackBaseBlock,
    SlackBaseField,
    SlackCodeBlock,
    SlackMessage,
    SlackTextBlock,
    SlackTextField,
)

_ANSI_REGEX = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")
"""Regex that matches ANSI escape sequences."""

__all__ = [
    "CodeExecutionError",
    "ComparisonError",
    "FlockNotFoundError",
    "GafaelfawrParseError",
    "GafaelfawrWebError",
    "GitHubFileNotFoundError",
    "JupyterProtocolError",
    "JupyterTimeoutError",
    "JupyterWebError",
    "MobuMixin",
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


class MobuMixin:
    """Mixin class to add `event` and `monkey` fields to Exception."""

    def __init__(
        self, event: str | None = None, monkey: str | None = None
    ) -> None:
        self.mobu_init()

    def mobu_init(
        self, event: str | None = None, monkey: str | None = None
    ) -> None:
        """Initialize mobu-specific fields."""
        self.event: str | None = event
        self.monkey: str | None = monkey

    def mobu_fields(self) -> list[SlackBaseField]:
        fields: list[SlackBaseField] = []
        if self.event:
            fields.append(SlackTextField(heading="Event", text=self.event))
        if self.monkey:
            fields.append(SlackTextField(heading="Monkey", text=self.monkey))
        return fields


class GafaelfawrParseError(ne.NubladoClientSlackException):
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

    @override
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


class GafaelfawrWebError(ne.NubladoClientSlackWebException):
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


class MobuSlackException(ne.NubladoClientSlackException, MobuMixin):
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
    failed_at
        When the operation that ended in an exception failed
        (defaults to the current time).
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
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
        monkey: str | None = None,
        event: str | None = None,
    ) -> None:
        super().__init__(msg, user, failed_at=failed_at, started_at=started_at)
        self.mobu_init(monkey=monkey, event=event)

    @classmethod
    def from_slack_exception(cls, exc: ne.NubladoClientSlackException) -> Self:
        return cls(
            msg=exc.message,
            user=exc.user,
            started_at=exc.started_at,
            failed_at=exc.failed_at,
        )

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        image = self.annotations.get("image")
        if image:
            fields.append(SlackTextField(heading="Image", text=image))
        return fields

    @override
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


class MobuSlackWebException(
    ne.NubladoClientSlackWebException, MobuSlackException
):
    """Represents an exception that can be reported to Slack.

    Similar to `MobuSlackException`, this adds some additional fields to
    `~rubin.nublado.client.SlackWebException` but is otherwise equivalent. It
    is intended to be subclassed. Subclasses may want to override the
    `to_slack` method.
    """

    @override
    def common_blocks(self) -> list[SlackBaseBlock]:
        blocks = MobuSlackException.common_blocks(self)
        if self.url:
            text = f"{self.method} {self.url}" if self.method else self.url
            blocks.append(SlackTextBlock(heading="URL", text=text))
        return blocks


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

    @override
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


class CodeExecutionError(ne.CodeExecutionError, MobuMixin):
    """Error generated by code execution in a notebook on JupyterLab."""

    def __init__(
        self,
        *,
        user: str,
        code: str | None = None,
        code_type: str = "code",
        error: str | None = None,
        status: str | None = None,
        monkey: str | None = None,
        event: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> None:
        super().__init__(
            user=user,
            code=code,
            code_type=code_type,
            error=error,
            status=status,
            started_at=started_at,
            failed_at=failed_at,
        )
        self.mobu_init(monkey=monkey, event=event)

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

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.CodeExecutionError,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        CodeExecutionError
            Converted exception.
        """
        new_exc = cls(
            user=exc.user or "<user unknown>",
            code=exc.code,
            code_type=exc.code_type,
            error=exc.error,
            status=exc.status,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
            monkey=monkey,
            event=event,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc


class GitHubFileNotFoundError(Exception):
    """Tried to retrieve contents for a non-existent file in a GitHub
    repo.
    """


class JupyterProtocolError(ne.JupyterProtocolError, MobuMixin):
    """Some error occurred when talking to JupyterHub or JupyterLab."""

    def __init__(
        self,
        msg: str,
        user: str | None = None,
        *,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
        monkey: str | None = None,
        event: str | None = None,
    ) -> None:
        super().__init__(
            msg=msg, user=user, started_at=started_at, failed_at=failed_at
        )
        self.mobu_init(monkey=monkey, event=event)

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.JupyterProtocolError,
        event: str | None = None,
        monkey: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
        annotations: dict[str, str] | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterProtocolError
            Converted exception.
        """
        new_exc = cls(
            msg=exc.message,
            user=exc.user,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
            monkey=monkey,
            event=event,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields


class JupyterSpawnError(ne.JupyterSpawnError, MobuMixin):
    """The Jupyter Lab pod failed to spawn."""

    def __init__(
        self,
        log: str,
        user: str,
        message: str | None = None,
        monkey: str | None = None,
        event: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> None:
        if message:
            message = f"Spawning lab failed: {message}"
        else:
            message = "Spawning lab failed"
        super().__init__(
            message, user, started_at=started_at, failed_at=failed_at
        )
        self.log = log
        self.mobu_init(monkey=monkey, event=event)

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.JupyterSpawnError,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterSpawnError
            Converted exception.
        """
        new_exc = cls(
            log=exc.log,
            user=exc.user or "<user unknown>",
            message=exc.message,
            monkey=monkey,
            event=event,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc

    @classmethod
    def from_exception(
        cls,
        log: str,
        exc: Exception,
        user: str,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
        *,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
    ) -> Self:
        """Convert from an arbitrary exception to a spawn error.

        Parameters
        ----------
        log
            Log of the spawn to this point.
        exc
            Exception that terminated the spawn attempt.
        user
            Username of the user spawning the lab.
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterSpawnError
            Converted exception.
        """
        client_exc = super().from_exception(log, exc, user)
        new_exc = cls.from_client_exception(
            client_exc,
            monkey=monkey,
            event=event,
            started_at=started_at or client_exc.started_at,
            failed_at=failed_at or client_exc.failed_at,
        )
        new_exc.annotations.update(client_exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields


class JupyterTimeoutError(ne.JupyterTimeoutError, MobuMixin):
    """Timed out waiting for the lab to spawn."""

    def __init__(
        self,
        msg: str,
        user: str,
        log: str | None = None,
        *,
        monkey: str | None = None,
        event: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> None:
        super().__init__(msg, user, started_at=started_at, failed_at=failed_at)
        self.log = log
        self.mobu_init(monkey=monkey, event=event)

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.JupyterTimeoutError,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterTimeoutError
            Converted exception.
        """
        new_exc = cls(
            log=exc.log,
            user=exc.user or "<user unknown>",
            msg=exc.message,
            monkey=monkey,
            event=event,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc


class JupyterWebError(ne.JupyterWebError, MobuMixin):
    """An error occurred when talking to JupyterHub or a Jupyter lab."""

    def __init__(
        self,
        msg: str,
        user: str | None = None,
        *,
        monkey: str | None = None,
        event: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> None:
        super().__init__(
            message=msg, user=user, started_at=started_at, failed_at=failed_at
        )
        self.mobu_init(monkey=monkey, event=event)

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.JupyterWebError,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterWebError
            Converted exception.
        """
        new_exc = cls(
            msg=exc.message,
            user=exc.user,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
            monkey=monkey,
            event=event,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        new_exc.event = event
        new_exc.method = exc.method
        new_exc.url = exc.url
        new_exc.body = exc.body
        return new_exc

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields


class JupyterWebSocketError(ne.JupyterWebSocketError, MobuMixin):
    """An error occurred talking to the Jupyter lab WebSocket."""

    def __init__(
        self,
        msg: str,
        *,
        user: str,
        code: int | None = None,
        reason: str | None = None,
        status: int | None = None,
        body: bytes | None = None,
        monkey: str | None = None,
        event: str | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> None:
        super().__init__(
            msg=msg,
            user=user,
            code=code,
            reason=reason,
            status=status,
            started_at=started_at,
            failed_at=failed_at,
            body=body,
        )
        self.mobu_init(monkey=monkey, event=event)

    @override
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

    @override
    def common_fields(self) -> list[SlackBaseField]:
        """Return common fields to put in any alert.

        Returns
        -------
        list of SlackBaseField
            Common fields to add to the Slack message.
        """
        fields = super().common_fields()
        fields.extend(self.mobu_fields())
        return fields

    @classmethod
    def from_client_exception(
        cls,
        exc: ne.JupyterWebSocketError,
        monkey: str | None = None,
        event: str | None = None,
        annotations: dict[str, str] | None = None,
        started_at: datetime.datetime | None = None,
        failed_at: datetime.datetime | None = None,
    ) -> Self:
        """
        Add Mobu-specific fields to exception from NubladoClient layer.

        Parameters
        ----------
        exc
            Original exception
        monkey
            Monkey spawning the lab, if known.
        event
            Event (from mobu's perspective) spawning the lab, if known.
        annotations
            Additional annotations
        started_at
            Timestamp for beginning of operation that caused the exception,
            if known.
        failed_at
            Timestamp for failure of operation that caused the exception,
            if known (defaults to the current time).

        Returns
        -------
        JupyterWebSocketError
            Converted exception.
        """
        body = exc.body
        if body is not None:
            body_bytes = body.encode()
        new_exc = cls(
            msg=exc.message,
            user=exc.user or "<user unknown>",
            code=exc.code,
            reason=exc.reason,
            status=exc.status,
            body=body_bytes,
            monkey=monkey,
            event=event,
            started_at=started_at or exc.started_at,
            failed_at=failed_at or exc.failed_at,
        )
        new_exc.annotations.update(exc.annotations or {})
        new_exc.annotations.update(annotations or {})
        return new_exc


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

    @override
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
