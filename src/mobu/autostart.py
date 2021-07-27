"""Support for automatically starting flocks."""

from __future__ import annotations

import yaml

from .config import config
from .dependencies.manager import monkey_business_manager
from .models.flock import FlockConfig


async def autostart() -> None:
    """Automatically start configured flocks.

    This function should be called from the startup hook of the FastAPI
    application.
    """
    if not config.autostart:
        return

    with open(config.autostart, "r") as f:
        autostart = yaml.safe_load(f)
    flock_configs = [FlockConfig.parse_obj(flock) for flock in autostart]

    for flock_config in flock_configs:
        await monkey_business_manager.start_flock(flock_config)
