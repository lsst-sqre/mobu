"""Models for monkey business."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..constants import NOTEBOOK_REPO_BRANCH, NOTEBOOK_REPO_URL
from ..models.timings import StopwatchData

__all__ = ["BusinessConfig", "BusinessData"]


class BusinessConfig(BaseModel):
    """Configuration for monkey business.

    Notes
    -----
    Ideally there would be separate configuration models for each type of
    business so that we didn't accept parameters that weren't supported by the
    business being requested, but getting the typing to work such that
    Pydantic can do that automatically turned into too much of a tangle.  This
    therefore represents the superset of all possible business configuration
    options.
    """

    nb_url: str = Field("/nb/", title="URL prefix for Jupyter")

    jupyter_options_form: Dict[str, str] = Field(
        default_factory=dict, title="Values to POST to the spawn options form"
    )

    code: str = Field(
        'print(2+2, end="")',
        title="Python code to execute",
        description="Only used by JupyterPythonLoop",
        example='print(2+2, end="")',
    )

    repo_url: str = Field(
        NOTEBOOK_REPO_URL,
        title="Git URL of notebook repository to execute",
        description="Only used by the NotebookRunner",
    )

    repo_branch: str = Field(
        NOTEBOOK_REPO_BRANCH,
        title="Git branch of notebook repository to execute",
        description="Only used by the NotebookRunner",
    )

    settle_time: int = Field(
        10,
        title="How long to wait after lab creation in seconds",
        description=(
            "Only used by the NotebookRunner. It will wait for this long"
            " after lab creation before trying to create a session."
        ),
        example=10,
    )

    idle_time: int = Field(
        60,
        title="How long to wait between business executions",
        description=(
            "AFter each loop executing monkey business, the monkey will"
            " pause for this long in seconds"
        ),
        example=60,
    )

    login_idle_time: int = Field(
        60,
        title="Time to pause after spawning lab",
        description=(
            "Only used by JupyterLoginLoop and JupyterJitterLoginLoop."
            " How long to wait after spawning the lab before destroying"
            " it again."
        ),
        example=60,
    )

    execution_idle_time: int = Field(
        1,
        title="How long to wait between cell executions in seconds",
        description="Used by JupyterPythonLoop and NotebookRunner",
        example=1,
    )

    reauth_interval: int = Field(
        30 * 60,
        title="Time between reauthentication attempts in seconds",
        description=(
            "Used by JupyterLoginLoop, JupyterPythonLoop, and NotebookRunner."
            " JupyterHub appears to issue tokens with a one hour lifetime."
        ),
        example=30 * 60,
    )

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            "For JupyterPythonLoop, this is the number of code snippets to"
            " execute before restarting the lab. For NotebookRunner, it's"
            " the number of notebooks."
        ),
        example=25,
    )

    delete_lab: bool = Field(
        True,
        title="Whether to delete the lab between iterations",
        description=(
            "By default, the lab is deleted and recreated after each"
            " iteration of monkey business involving JupyterLab. Set this"
            " to False to keep the same lab."
        ),
        example=True,
    )


class BusinessData(BaseModel):
    """Status of a running business."""

    name: str = Field(..., title="Type of business", example="Business")

    failure_count: int = Field(..., title="Number of failures", example=0)

    success_count: int = Field(..., title="Number of successes", example=25)

    timings: List[StopwatchData] = Field(..., title="Timings of events")

    notebook: Optional[str] = Field(
        None,
        title="Name of the currently running notebook",
        description="Will not be present if no notebook is being executed",
        example="cluster.ipynb",
    )

    running_code: Optional[str] = Field(
        None,
        title="Currently running code from the notebook",
        description="Will not be present if no code is being executed",
        example='import json\nprint(json.dumps({"foo": "bar"})\n',
    )
