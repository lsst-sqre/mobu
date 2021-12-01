"""Models for monkey business."""

from typing import List, Optional

from pydantic import BaseModel, Field

from ..constants import NOTEBOOK_REPO_BRANCH, NOTEBOOK_REPO_URL
from .jupyter import JupyterConfig, JupyterImage
from .timings import StopwatchData

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

    jupyter: JupyterConfig = Field(
        default_factory=JupyterConfig,
        title="Jupyter lab spawning configuration",
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

    working_directory: Optional[str] = Field(
        None,
        title="Working directory when running code",
        description="Used by JupyterPythonLoop and its subclasses",
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

    idle_time: int = Field(
        60,
        title="How long to wait between business executions",
        description=(
            "AFter each loop executing monkey business, the monkey will"
            " pause for this long in seconds"
        ),
        example=60,
    )

    spawn_settle_time: int = Field(
        10,
        title="How long to wait before polling spawn progress in seconds",
        description=(
            "Wait this long after triggering a lab spawn before starting to"
            " poll its progress. KubeSpawner 1.1.0 has a bug where progress"
            " queries prior to starting the spawn will fail with an exception"
            " that closes the progress EventStream."
        ),
        example=10,
    )

    lab_settle_time: int = Field(
        0,
        title="How long to wait after spawn before using a lab, in seconds",
        description=(
            "Wait this long after a lab successfully spawns before starting"
            " to use it"
        ),
        example=0,
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

    spawn_timeout: int = Field(
        610,
        title="Timeout for spawning a lab in seconds",
        description="Used by JupyterLoginLoop and its subclasses",
        example=610,
    )

    delete_timeout: int = Field(
        60,
        title="Timeout for deleting a lab in seconds",
        description="Used by JupyterLoginLoop and its subclasses",
        example=60,
    )

    max_executions: int = Field(
        25,
        title="How much to execute in a given lab and session",
        description=(
            "For JupyterPythonLoop, this is the number of code snippets to"
            " execute before restarting the lab. For NotebookRunner, it's"
            " the number of complete notebooks. NotebookRunner goes through"
            " the directory of notebooks one-by-one, running the entirety"
            " of each one and starting again at the beginning of the list"
            " when it runs out, until it has executed a total of"
            " max_executions notebooks. It then closes the session (and"
            " optionally deletes and recreates the lab, controlled by"
            " delete_lab), and then picks up where it left off."
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

    image: Optional[JupyterImage] = Field(
        None,
        title="JupyterLab image information",
        description="Will only be present when there is an active Jupyter lab",
    )

    notebook: Optional[str] = Field(
        None,
        title="Name of the currently running notebook",
        description="Will not be present if no notebook is being executed",
        example="cluster.ipynb",
    )

    running_code: Optional[str] = Field(
        None,
        title="Currently running code",
        description="Will not be present if no code is being executed",
        example='import json\nprint(json.dumps({"foo": "bar"})\n',
    )
