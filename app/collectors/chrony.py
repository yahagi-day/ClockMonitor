import asyncio
import time

from app import config
from app.collectors.base import PeriodicCollector

# chronyc -c tracking CSV field order (chrony 4.x)
_TRACKING_FIELDS = [
    "ref_id", "ref_name", "stratum", "ref_time_epoch",
    "system_time_s", "last_offset_s", "rms_offset_s",
    "frequency_ppm", "residual_freq_ppm", "skew_ppm",
    "root_delay_s", "root_dispersion_s", "update_interval_s", "leap_status",
]

# chronyc -c sources CSV field order
_SOURCE_FIELDS = [
    "mode", "state", "name", "stratum", "poll",
    "reach_octal", "last_rx_s",
    "last_sample_offset_s", "last_sample_actual_offset_s", "last_sample_err_s",
]


async def _run_chronyc(*args: str, timeout: float = 2.0) -> str:
    proc = await asyncio.create_subprocess_exec(
        "chronyc", "-c", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode()


async def _run_chronyc_sudo(*args: str, timeout: float = 5.0) -> str:
    proc = await asyncio.create_subprocess_exec(
        "sudo", "chronyc", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode()


def _parse_serverstats(text: str) -> dict:
    result: dict = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        try:
            result[key.strip().lower().replace(" ", "_")] = int(val.strip())
        except ValueError:
            pass
    return result


def _parse_clients(text: str) -> list[dict]:
    clients = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("==="):
            in_table = True
            continue
        if not in_table or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        try:
            clients.append({
                "hostname": parts[0],
                "ntp_rx": int(parts[1]),
                "ntp_drop": int(parts[2]),
                "last_ntp": parts[5],
            })
        except (ValueError, IndexError):
            pass
    return clients


def _parse_tracking(csv: str) -> dict:
    parts = csv.strip().split(",")
    if len(parts) < len(_TRACKING_FIELDS):
        raise ValueError(f"tracking: expected {len(_TRACKING_FIELDS)} fields, got {len(parts)}")
    d: dict = {}
    for i, key in enumerate(_TRACKING_FIELDS):
        val = parts[i]
        if key in {"stratum"}:
            d[key] = int(val)
        elif key == "leap_status":
            d[key] = val
        elif key in {"ref_id", "ref_name"}:
            d[key] = val
        else:
            d[key] = float(val)
    return d


def _parse_sources(text: str) -> list[dict]:
    sources = []
    for line in text.strip().splitlines():
        parts = line.split(",")
        if len(parts) < len(_SOURCE_FIELDS):
            continue
        d: dict = {}
        for i, key in enumerate(_SOURCE_FIELDS):
            val = parts[i]
            if key in {"stratum", "poll"}:
                d[key] = int(val)
            elif key in {"last_rx_s", "last_sample_offset_s",
                         "last_sample_actual_offset_s", "last_sample_err_s"}:
                try:
                    d[key] = float(val)
                except ValueError:
                    d[key] = 0.0
            else:
                d[key] = val
        sources.append(d)
    return sources


class ChronyCollector(PeriodicCollector):
    name = "chrony"
    interval = config.CHRONY_TRACKING_INTERVAL

    def __init__(self):
        self._last_sources_time: float = 0.0
        self._last_serverstats_time: float = 0.0
        self._last_clients_time: float = 0.0
        self._cached_sources: list[dict] = []
        self._cached_serverstats: dict = {}
        self._cached_clients: list[dict] = []

    async def tick(self, storage) -> None:
        raw = await _run_chronyc("tracking")
        tracking = _parse_tracking(raw)

        now = time.monotonic()
        if now - self._last_sources_time >= config.CHRONY_SOURCES_INTERVAL:
            raw_src = await _run_chronyc("sources")
            self._cached_sources = _parse_sources(raw_src)
            self._last_sources_time = now

        if now - self._last_serverstats_time >= config.CHRONY_SERVERSTATS_INTERVAL:
            try:
                raw_ss = await _run_chronyc_sudo("serverstats")
                self._cached_serverstats = _parse_serverstats(raw_ss)
            except Exception:
                pass
            self._last_serverstats_time = now

        if now - self._last_clients_time >= config.CHRONY_CLIENTS_INTERVAL:
            try:
                raw_cl = await _run_chronyc_sudo("clients")
                self._cached_clients = _parse_clients(raw_cl)
            except Exception:
                pass
            self._last_clients_time = now

        last_offset = tracking.get("last_offset_s", 0.0)
        selected = next(
            (s["name"] for s in self._cached_sources if s.get("state") == "*"),
            "",
        )
        has_selected = bool(selected)

        if abs(last_offset) > 1e-3:
            health = "red"
        elif abs(last_offset) > 1e-5 or not has_selected:
            health = "amber"
        else:
            health = "green"

        payload = {
            **tracking,
            "selected_source": selected,
            "sources": self._cached_sources,
            "serverstats": self._cached_serverstats,
            "clients": self._cached_clients,
        }
        storage.set_snapshot("chrony", payload, health)
        storage.append_series("chrony_offset", last_offset)
