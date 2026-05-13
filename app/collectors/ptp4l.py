import asyncio
import os
import re
from uuid import uuid4

from app import config
from app.collectors.base import PeriodicCollector

_PMC_TIMEOUT = 3.0
_JOURNAL_OFFSET_RE = re.compile(r"master offset\s+([-\d]+)\s+s\d+\s+freq")
_JOURNAL_STATE_RE = re.compile(r"port \d+: (\w+) to (\w+)")


async def _run_pmc(command: str) -> str:
    tmp = f"/tmp/clockmonitor.pmc.{uuid4().hex[:8]}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "pmc", "-u",
            "-s", config.PTP4L_RO_SOCKET,
            "-i", tmp,
            "-b", "0",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PMC_TIMEOUT)
        return stdout.decode()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _parse_pmc_block(text: str) -> dict:
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("sending") or line.startswith("pmc"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


async def _pmc_snapshot() -> dict | None:
    try:
        cds_raw = await _run_pmc("GET CURRENT_DATA_SET")
        pds_raw = await _run_pmc("GET PORT_DATA_SET")
    except Exception:
        return None

    cds = _parse_pmc_block(cds_raw)
    pds = _parse_pmc_block(pds_raw)

    if not cds and not pds:
        return None

    try:
        offset_ns = float(cds.get("offsetFromMaster", "0.0").rstrip("ns").strip())
    except ValueError:
        offset_ns = 0.0
    try:
        delay_ns = float(cds.get("meanPathDelay", "0.0").rstrip("ns").strip())
    except ValueError:
        delay_ns = 0.0

    return {
        "port_state": pds.get("portState", ""),
        "offset_from_master_ns": offset_ns,
        "mean_path_delay_ns": delay_ns,
        "steps_removed": int(cds.get("stepsRemoved", 0)),
        "port_identity": pds.get("portIdentity", ""),
        "data_source": "pmc",
    }


async def _journal_snapshot() -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", "ptp4l", "-n", "200", "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        text = stdout.decode()
    except Exception:
        return None

    offset_ns: float = 0.0
    port_state: str = ""

    for line in reversed(text.splitlines()):
        if not offset_ns:
            m = _JOURNAL_OFFSET_RE.search(line)
            if m:
                offset_ns = float(m.group(1))
        if not port_state:
            m = _JOURNAL_STATE_RE.search(line)
            if m:
                port_state = m.group(2)
        if offset_ns and port_state:
            break

    if not offset_ns and not port_state:
        return None

    return {
        "port_state": port_state,
        "offset_from_master_ns": offset_ns,
        "mean_path_delay_ns": 0.0,
        "steps_removed": 0,
        "port_identity": "",
        "data_source": "journal",
    }


class Ptp4lCollector(PeriodicCollector):
    name = "ptp4l"
    interval = config.PTP_INTERVAL

    async def tick(self, storage) -> None:
        snap = await _pmc_snapshot()
        if snap is None:
            snap = await _journal_snapshot()
        if snap is None:
            storage.set_snapshot("ptp4l", {"error": "no data", "data_source": "error"}, "red")
            return

        port_state = snap.get("port_state", "")
        offset_ns = snap.get("offset_from_master_ns", 0.0)

        _green_states = {"MASTER"}
        _amber_states = {"LISTENING", "PRE_MASTER", "UNCALIBRATED", "SLAVE"}
        _red_states = {"FAULTY", "DISABLED", "INITIALIZING"}

        if port_state in _green_states and abs(offset_ns) < 1000:
            health = "green"
        elif port_state in _amber_states or port_state in _green_states:
            health = "amber"
        elif port_state in _red_states:
            health = "red"
        else:
            health = "amber"

        storage.set_snapshot("ptp4l", snap, health)
        storage.append_series("ptp_offset_from_master", offset_ns)
