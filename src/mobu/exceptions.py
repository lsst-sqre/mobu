"""Exceptions for mobu."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from fastapi import status
from pydantic import ValidationError
from safir.fastapi import ClientRequestError
from safir.models import ErrorLocation
from safir.sentry import SentryException, SentryWebException

__all__ = [
    "ComparisonError",
    "FlockNotFoundError",
    "GafaelfawrParseError",
    "GafaelfawrWebError",
    "GitHubFileNotFoundError",
    "MonkeyNotFoundError",
    "NotRetainingLogsError",
    "SIAClientError",
    "SubprocessError",
]


class GafaelfawrParseError(SentryException):
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
        super().__init__(message)
        if user:
            self.contexts["validation_info"] = {"error": error}

        self.error = error


class GafaelfawrWebError(SentryWebException):
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


class NotRetainingLogsError(ClientRequestError):
    """Mobu is not configured to retain logs."""

    error = "mobu_not_retaining_logs"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        msg = "Mobu is not configured to retain monkey logs"
        super().__init__(msg)


class NotebookRepositoryError(Exception):
    """The repository containing notebooks to run is not valid."""


class RepositoryConfigError(Exception):
    """The in-repo mobu.yaml config file is invalid."""


class GitHubFileNotFoundError(Exception):
    """Tried to retrieve contents for a non-existent file in a GitHub
    repo.
    """


class SubprocessError(SentryException):
    """Running a subprocess failed."""

    def __init__(
        self,
        msg: str,
        *,
        returncode: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        super().__init__(msg)
        self.msg = msg
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.cwd = cwd
        self.env = env

        self.contexts["subprocess_info"] = {
            "return_code": str(self.returncode),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "directory": str(self.cwd),
            "env": self.env,
        }

    def __str__(self) -> str:
        return (
            f"{self.msg} with rc={self.returncode};"
            f" stdout='{self.stdout}'; stderr='{self.stderr}'"
            f" cwd='{self.cwd}'; env='{self.env}'"
        )


class ComparisonError(SentryException):
    """Comparing two strings failed."""

    def __init__(
        self,
        *,
        expected: str,
        received: str,
    ) -> None:
        super().__init__("Comparison failed")
        self.expected = expected
        self.received = received

        self.contexts["comparison_info"] = {
            "expected": self.expected,
            "received": self.received,
        }

    def __str__(self) -> str:
        return (
            f"Comparison failed: expected '{self.expected}', but"
            f" received '{self.received}'"
        )


class JupyterSpawnTimeoutError(Exception):
    """Timed out waiting for the lab to spawn."""


class JupyterDeleteTimeoutError(Exception):
    """Timed out waiting for a lab to delete."""


class JupyterSpawnError(Exception):
    """The Jupyter Lab pod failed to spawn."""


class NotebookCellExecutionError(Exception):
    """Error when executing a notebook cell."""


class SIAClientError(Exception):
    """Creating an SIA client failed."""

    def __init__(self, exc: Exception) -> None:
        if str(exc):
            error = f"{type(exc).__name__}: {exc!s}"
        else:
            error = type(exc).__name__
        msg = f"Unable to create SIA client: {error}"
        super().__init__(msg)


class TAPClientError(Exception):
    """Creating a TAP client failed."""

    def __init__(self, exc: Exception) -> None:
        if str(exc):
            error = f"{type(exc).__name__}: {exc!s}"
        else:
            error = type(exc).__name__
        msg = f"Unable to create TAP client: {error}"
        super().__init__(msg)
