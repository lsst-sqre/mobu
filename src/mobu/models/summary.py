"""Combined summary of different functionalities."""

from pydantic import BaseModel, Field

from .ci_manager import CiManagerSummary
from .flock import FlockSummary


class CombinedSummary(BaseModel):
    """Summary of all app state."""

    flocks: list[FlockSummary] = Field(
        ..., title="Info about all running flocks"
    )
    ci_manager: CiManagerSummary | None = Field(
        None, title="Info about GitHub CI workers"
    )
