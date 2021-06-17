"""JupyterLoginLoop business logic for mobu.

This is a loop that will constantly try to spawn new
jupyter labs on a nublado instance, and then delete it."""

__all__ = [
    "JupyterLoginLoop",
]

import asyncio
from dataclasses import dataclass, field

from mobu.businesstime import BusinessTime
from mobu.jupyterclient import JupyterClient
from mobu.timing import LabLoopTimingData, TimeInfo


@dataclass
class JupyterLoginLoop(BusinessTime):
    success_count: int = 0
    failure_count: int = 0
    _client: JupyterClient = field(init=False)

    async def run(self) -> None:
        try:
            logger = self.monkey.log
            logger.info("Starting up...")
            self._client = JupyterClient(
                self.monkey.user, logger, self.options
            )
            stamp = LabLoopTimingData(start=TimeInfo.stamp(previous=None))
            self.timings.append(stamp)
            await self._client.hub_login()
            stamp.login_complete = TimeInfo.stamp(previous=stamp.start)
            logger.info("Logged into hub")
            last = stamp.login_complete
            while True:
                logger.info("Starting next iteration")
                tlc = LabLoopTimingData(start=TimeInfo.stamp(previous=last))
                self.timings.append(tlc)
                await self._client.ensure_lab()
                tlc.lab_created = TimeInfo.stamp(previous=tlc.start)
                logger.info("Lab created.")
                await asyncio.sleep(60)
                tlc.lab_complete = TimeInfo.stamp(previous=tlc.lab_created)
                logger.info("Deleting lab.")
                await self._client.delete_lab()
                tlc.lab_deleted = TimeInfo.stamp(previous=tlc.lab_complete)
                self.success_count += 1
                logger.info("Lab successfully deleted.")
                await asyncio.sleep(60)
                tlc.stop = TimeInfo.stamp(previous=tlc.lab_deleted)
                last = tlc.stop
        except Exception:
            self.failure_count += 1
            raise

    async def stop(self) -> None:
        await self._client.delete_lab()

    def dump(self) -> dict:
        r = super().dump()
        r.update(
            {
                "name": "JupyterLoginLoop",
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "jupyter_client": self._client.dump(),
            }
        )
        return r
