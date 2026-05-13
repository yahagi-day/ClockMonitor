import asyncio
import logging

logger = logging.getLogger(__name__)


class PeriodicCollector:
    name: str = "base"
    interval: float = 1.0

    async def run(self, storage) -> None:
        while True:
            try:
                await self.tick(storage)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("%s collector error: %s", self.name, e)
                storage.set_snapshot(self.name, {"error": str(e)}, "red")
            await asyncio.sleep(self.interval)

    async def tick(self, storage) -> None:
        raise NotImplementedError
