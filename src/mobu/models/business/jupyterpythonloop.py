"""Models for the JupyterPythonLoop monkey business and subclasses."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .base import BusinessConfig
from .jupyterloginloop import JupyterLoginOptions

__all__ = [
    "JupyterPythonExecutorOptions",
    "JupyterPythonLoopConfig",
    "JupyterPythonLoopOptions",
]


class JupyterPythonExecutorOptions(JupyterLoginOptions):
    """Options for any business executing Python code in a loop."""

    execution_idle_time: int = Field(
        1,
        title="How long to wait between cell executions in seconds",
        description="Used by JupyterPythonLoop and NotebookRunner",
        example=1,
    )

    get_node: bool = Field(
        True,
        title="Whether to get the node name for error reporting",
        description=(
            "Used by JupyterPythonLoop and its subclasses. Requires the lab"
            " have rubin_jupyter_utils.lab.notebook.utils pre-installed and"
            " able to make Kubernetes API calls."
        ),
    )

    working_directory: Optional[str] = Field(
        None,
        title="Working directory when running code",
        example="notebooks/tutorial-notebooks",
    )


class JupyterPythonLoopOptions(JupyterPythonExecutorOptions):
    """Options for JupyterPythonLoop monkey business."""

    code: str = Field(
        'print(2+2, end="")',
        title="Python code to execute",
        example='print(2+2, end="")',
    )

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            "The number of code snippets to execute before restarting the lab."
        ),
        example=25,
    )


class JupyterPythonLoopConfig(BusinessConfig):
    """Configuration specialization for JupyterLoginLoop."""

    type: Literal["JupyterPythonLoop"] = Field(
        ..., title="Type of business to run"
    )

    options: JupyterPythonLoopOptions = Field(
        default_factory=JupyterPythonLoopOptions,
        title="Options for the monkey business",
    )
