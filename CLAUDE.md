# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ClockMonitor is a read-only FastAPI web dashboard (port 8080) for a Raspberry Pi 5 running as:
- **Stratum 1 NTP server** — chrony disciplined by GPS/PPS (GT-502MGG-N receiver, GPIO18)
- **PTP Grandmaster Clock** — ptp4l + phc2sys on eth0 (AES67/Dante profile)

## Running the app

```bash
# Development (from /home/yahagi_day/ClockMonitor)
source .venv/bin/activate
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Service management
sudo systemctl restart clockmonitor
sudo systemctl status clockmonitor
journalctl -u clockmonitor -f
```

The venv uses `--system-site-packages` to inherit `gps==3.25` and `Jinja2==3.1.6` from the system. Do not add these to `requirements.txt`.

## Architecture

Single asyncio process. At startup, five `PeriodicCollector` tasks run concurrently and write into a shared `Storage` singleton (`app.state.storage`). HTTP handlers only read from `Storage` — they never invoke subprocesses directly.

```
Collectors (background tasks)       Storage            API
  ChronyCollector  1s/5s/10s/30s ─┐
  GpsdCollector    1s tick        ─┤  snapshots[]   GET /api/status
  Ptp4lCollector   2s             ─┼─ buffers{}  ── GET /api/history
  PpsCollector     1s             ─┤  health{}      GET /api/stream (SSE)
  SystemdCollector 5s             ─┘
```

**`app/storage.py`** — `RingBuffer` (deque of `(epoch, value)` tuples, maxlen=3600) + `Storage` singleton with `snapshots`, `health`, and named `buffers`. No locking needed (CPython GIL + single-writer pattern).

**`app/collectors/base.py`** — `PeriodicCollector`: `run()` loops forever calling `tick()` then `asyncio.sleep(interval)`. Exceptions in `tick()` are caught and written as `health="red"` snapshots.

**`app/routers/api.py`** — `GET /api/stream` uses `sse_starlette.EventSourceResponse` pushing JSON snapshots every `SSE_PUSH_INTERVAL`. History source names are whitelisted in `HISTORY_SOURCES`.

**`static/app.js`** — Plain ES module. Opens `EventSource("/api/stream")`, updates DOM via `data-field` attributes and direct IDs, pushes to three Chart.js instances (max 600 points each). On load, prefetches 10 min of history for each chart.

## Collector specifics

**ChronyCollector** — `chronyc -c tracking` (CSV, every 1s). `chronyc -c sources` every 5s. `sudo chronyc serverstats` / `sudo chronyc clients` every 10s/30s — requires the sudoers rule in `/etc/sudoers.d/clockmonitor`. Regular `chronyc` commands use `-c` flag for CSV output; `sudo` is needed because the chrony command socket at `/run/chrony/` is `drwx------` owned by `_chrony`.

**GpsdCollector** — Long-lived `gpspipe -w` subprocess reads JSON lines in a background task. SKY messages have two forms: compact (`uSat`/`nSat` only) and full (with `satellites` array). Satellite counts fall back to `sky.get("uSat")` when the array is absent.

**Ptp4lCollector** — Calls `pmc` with `-i /tmp/clockmonitor.pmc.<uuid>` to avoid binding to the default `/var/run/pmc.<pid>` path (root-only). Uses the read-only socket `/var/run/ptp4lro`. Falls back to parsing `journalctl -u ptp4l` if pmc fails; snapshot carries `data_source: "journal"` in that case.

**PpsCollector** — Reads `/sys/class/pps/pps0/assert` (format: `sec.nsec#seq`). Computes Hz from Δseq/Δt between ticks.

## Health rules

| Source | green | amber | red |
|---|---|---|---|
| chrony | `\|offset\| ≤ 10µs` AND `*` source present | `\|offset\| > 10µs` OR no `*` source | `\|offset\| > 1ms` |
| gpsd | mode=3 AND sats≥4 | mode=3 (no SKY yet) OR mode=2 | mode≤1 |
| ptp4l | MASTER AND `\|offset\| < 1000ns` | LISTENING/PRE_MASTER/SLAVE | FAULTY/DISABLED |
| pps | seq advancing AND 0.9≤Hz≤1.1 | Hz out of band | seq stale >3s |
| systemd | all 4 active | 1 not active | 2+ not active |

## System context

- `/etc/chrony/chrony.conf` — `cmdallow 127.0.0.1` + `bindcmdaddress 127.0.0.1` added for serverstats access
- `/etc/sudoers.d/clockmonitor` — `yahagi_day ALL=(root) NOPASSWD: /usr/bin/chronyc`
- `/var/run/ptp4lro` — ptp4l read-only UDS socket (world-writable, exists by default)
- `/sys/class/pps/pps0/assert` — world-readable PPS assert timestamp
- The systemd service drops `NoNewPrivileges` to allow sudo for chronyc
- GPS source state `x` (falseticker, ~360ms offset) in chrony sources is normal — NMEA serial latency; PPS provides the actual sub-µs lock
