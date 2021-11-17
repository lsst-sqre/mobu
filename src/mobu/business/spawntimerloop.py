"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new Jupyter labs on a nublado
instance, and then delete them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import JupyterSpawnError, JupyterTimeoutError
from .jupyterloginloop import JupyterLoginLoop, ProgressLogMessage

if TYPE_CHECKING:
    from typing import Dict, List

    from structlog import BoundLogger

    from ..models.business import BusinessConfig, BusinessData
    from ..user import AuthenticatedUser
__all__ = ["SpawnTimerLoop"]


class SpawnTimerLoop(JupyterLoginLoop):
    """Business that logs on to the hub, creates a lab, and deletes it.
    This is just the standard JupyterLoginLoop with more timing probes,
    specifically including the messages we get while waiting to spawn.
    """

    def __init__(
        self,
        logger: BoundLogger,
        business_config: BusinessConfig,
        user: AuthenticatedUser,
    ) -> None:
        super().__init__(logger, business_config, user)
        # Add log_messages as an attribute so we can dump them and add
        #  them to annotations
        self.log_messages: List(ProgressLogMessage) = []

    def annotations(self) -> Dict[str, str]:
        """Timer annotations to use.

        Subclasses should override this to add more annotations based on
        current business state.  They should call ``super().annotations()``
        and then add things to the resulting dictionary.
        """
        anno = super().annotations()
        anno["log_messages"] = "\n".join([str(x) for x in self.log_messages])
        return anno

    async def spawn_lab(self) -> None:
        with self.timings.start("spawn_lab", self.annotations()) as sw:
            self.image = await self._client.spawn_lab()
            # Clear log messages
            self.log_messages = []

            # Pause before using the progress API, since otherwise it may not
            # have attached to the spawner and will not return a full stream
            # of events.  (It will definitely take longer than 5s for the lab
            # to spawn.)
            # Add timing.  Should be really boring.
            with self.timings.start("spawn_settle"):
                await self.pause(self.config.spawn_settle_time)
            if self.stopping:
                return

            # Watch the progress API until the lab has spawned.
            # Add timing.  Might not be boring.
            with self.timings.start("spawner_progress"):
                timeout = (
                    self.config.spawn_timeout - self.config.spawn_settle_time
                )
                progress = self._client.spawn_progress()
                async for message in self.iter_with_timeout(progress, timeout):
                    self.log_messages.append(
                        ProgressLogMessage(message.message)
                    )
                    if message.ready:
                        with self.timings.start(
                            "spawner_progress_finished", self.annotations()
                        ):
                            # Obviously this is fast.  We want the annotations.
                            return

            # We only fall through if the spawn failed, timed out, or if we're
            # stopping the business.
            if self.stopping:
                return
            log = "\n".join([str(m) for m in self.log_messages])
            if sw.elapsed.total_seconds() > timeout:
                elapsed = round(sw.elapsed.total_seconds())
                msg = f"Lab did not spawn after {elapsed}s"
                raise JupyterTimeoutError(self.user.username, msg, log)
            else:
                raise JupyterSpawnError(self.user.username, log)

    def dump(self) -> BusinessData:
        data = super().dump()
        data.progress_log_messages = [str(x) for x in self.log_messages]
        return data
