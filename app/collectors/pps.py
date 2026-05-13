import os
import time

from app import config
from app.collectors.base import PeriodicCollector

_STALE_THRESHOLD = 3.0


class PpsCollector(PeriodicCollector):
    name = "pps"
    interval = config.PPS_INTERVAL

    def __init__(self):
        self._prev: dict[str, tuple[int, float]] = {}  # path -> (seq, mono_time)

    async def tick(self, storage) -> None:
        devices: dict[str, dict] = {}
        now_mono = time.monotonic()

        for path in config.PPS_DEVICES:
            if not os.path.exists(path):
                continue
            try:
                raw = open(path).read().strip()
                # format: "seconds.nanoseconds#sequence"
                time_part, seq_str = raw.split("#")
                sec_str, nsec_str = time_part.split(".")
                seq = int(seq_str)
                epoch = float(sec_str) + float(nsec_str) * 1e-9

                name = os.path.basename(os.path.dirname(path))  # pps0 / pps1
                prev = self._prev.get(path)
                hz: float | None = None
                if prev is not None:
                    prev_seq, prev_mono = prev
                    dt = now_mono - prev_mono
                    dseq = seq - prev_seq
                    if dt > 0 and dseq >= 0:
                        hz = dseq / dt

                self._prev[path] = (seq, now_mono)
                devices[name] = {"seq": seq, "last_assert_epoch": epoch, "hz": hz}
            except Exception:
                name = os.path.basename(os.path.dirname(path))
                devices[name] = {"seq": 0, "last_assert_epoch": 0.0, "hz": None}

        if not devices:
            storage.set_snapshot("pps", {"devices": {}}, "red")
            return

        # Determine health from first device
        main_dev = devices.get("pps0") or next(iter(devices.values()))
        hz = main_dev.get("hz")
        epoch = main_dev.get("last_assert_epoch", 0.0)
        age = time.time() - epoch if epoch else _STALE_THRESHOLD + 1

        if age > _STALE_THRESHOLD:
            health = "red"
        elif hz is None or not (0.9 <= hz <= 1.1):
            health = "amber"
        else:
            health = "green"

        storage.set_snapshot("pps", {"devices": devices}, health)
        if "pps0" in devices:
            storage.append_series("pps0_seq", float(devices["pps0"]["seq"]))
