import asyncio
import json
import logging

from app import config
from app.collectors.base import PeriodicCollector

logger = logging.getLogger(__name__)


class GpsdCollector(PeriodicCollector):
    name = "gpsd"
    interval = config.CHRONY_TRACKING_INTERVAL  # 1 s tick

    def __init__(self):
        self._latest_tpv: dict = {}
        self._latest_sky: dict = {}
        self._reader_task: asyncio.Task | None = None

    async def run(self, storage) -> None:
        self._reader_task = asyncio.create_task(self._gpspipe_reader())
        await super().run(storage)

    async def _gpspipe_reader(self) -> None:
        while True:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "gpspipe", "-w",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    line = raw.decode(errors="replace").strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cls = msg.get("class", "")
                    if cls == "TPV":
                        self._latest_tpv = msg
                    elif cls == "SKY":
                        self._latest_sky = msg
                await proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("gpspipe reader error: %s", e)
            await asyncio.sleep(2.0)

    async def tick(self, storage) -> None:
        tpv = self._latest_tpv
        sky = self._latest_sky

        mode = tpv.get("mode", 0)
        sats: list[dict] = sky.get("satellites", [])

        # SKY has two forms:
        # - compact: {"uSat": N, "nSat": M} (no satellites array)
        # - full:    {"uSat": N, "nSat": M, "satellites": [...]}
        if sats:
            sats_used = sum(1 for s in sats if s.get("used", False))
            sats_visible = len(sats)
        else:
            sats_used = sky.get("uSat", 0)
            sats_visible = sky.get("nSat", sky.get("uSat", 0))

        no_sky_data = not sky  # no SKY message received at all
        if mode == 3 and sats_used >= 4:
            health = "green"
        elif mode == 3 and (no_sky_data or sats_used >= 1):
            health = "amber"  # valid fix, waiting for SKY or low sat count
        elif mode == 2 or (1 <= sats_used <= 3):
            health = "amber"
        else:
            health = "red"

        payload = {
            "mode": mode,
            "lat": tpv.get("lat"),
            "lon": tpv.get("lon"),
            "alt_m": tpv.get("alt"),
            "time": tpv.get("time"),
            "epx": tpv.get("epx"),
            "epy": tpv.get("epy"),
            "ept": tpv.get("ept"),
            "sats_used": sats_used,
            "sats_visible": sats_visible,
        }
        storage.set_snapshot("gpsd", payload, health)
        storage.append_series("gps_sat_used", float(sats_used))
        storage.append_series("gps_sat_visible", float(sats_visible))
