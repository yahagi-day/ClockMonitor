import time
from collections import deque
from typing import Literal

from app import config


class RingBuffer:
    def __init__(self, maxlen: int = config.RING_SECONDS):
        self._buf: deque[tuple[float, float | None]] = deque(maxlen=maxlen)

    def append(self, value: float | None) -> None:
        self._buf.append((time.time(), value))

    def since(self, seconds: float) -> list[tuple[float, float | None]]:
        cutoff = time.time() - seconds
        return [(t, v) for t, v in self._buf if t >= cutoff]

    def to_lists(self, seconds: float | None = None) -> dict:
        data = self.since(seconds) if seconds is not None else list(self._buf)
        if not data:
            return {"t": [], "v": []}
        ts, vs = zip(*data)
        return {"t": list(ts), "v": list(vs)}


class Storage:
    def __init__(self):
        self.snapshots: dict[str, dict] = {
            "chrony": {},
            "gpsd": {},
            "ptp4l": {},
            "pps": {},
            "systemd": {},
        }
        self.health: dict[str, str] = {
            "chrony": "amber",
            "gpsd": "amber",
            "ptp4l": "amber",
            "pps": "amber",
            "systemd": "amber",
        }
        self.buffers: dict[str, RingBuffer] = {
            "chrony_offset": RingBuffer(),
            "ptp_offset_from_master": RingBuffer(),
            "gps_sat_used": RingBuffer(),
            "gps_sat_visible": RingBuffer(),
            "pps0_seq": RingBuffer(),
        }

    def set_snapshot(
        self,
        source: str,
        payload: dict,
        health: Literal["green", "amber", "red"],
    ) -> None:
        self.snapshots[source] = payload
        self.health[source] = health

    def append_series(self, name: str, value: float | None) -> None:
        if name in self.buffers:
            self.buffers[name].append(value)

    def overall_health(self) -> str:
        order = {"red": 0, "amber": 1, "green": 2}
        worst = min(self.health.values(), key=lambda h: order.get(h, 1))
        return worst

    def get_status(self) -> dict:
        return {
            "now": time.time(),
            "health": dict(self.health),
            "overall_health": self.overall_health(),
            "chrony": self.snapshots["chrony"],
            "gpsd": self.snapshots["gpsd"],
            "ptp4l": self.snapshots["ptp4l"],
            "pps": self.snapshots["pps"],
            "systemd": self.snapshots["systemd"],
        }

    def get_history(self, name: str, minutes: int) -> dict:
        if name not in self.buffers:
            return {"name": name, "t": [], "v": []}
        data = self.buffers[name].to_lists(seconds=minutes * 60)
        return {"name": name, **data}
