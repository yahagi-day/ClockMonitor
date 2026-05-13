# ClockMonitor

Real-time web dashboard for a Raspberry Pi 5 operating as a Stratum 1 NTP server and PTP Grandmaster Clock.

Displays chrony, gpsd, ptp4l, PPS, and systemd service status in a browser, with 60-minute time-series graphs of offset and satellite count.

> 日本語版: [README_jp.md](README_jp.md)

## Monitored sections

| Section | Content |
|---|---|
| **System Clock** | System time offset, RMS, frequency error, reference source table |
| **NTP Server** | Packets received, client list |
| **GPS** | Fix mode, lat/lon, satellites used |
| **PTP** | portState, master offset, path delay |
| **PPS** | 1 Hz pulse heartbeat, sequence number |
| **Services** | Active state of chrony / gpsd / ptp4l / phc2sys |

## Prerequisites

All four services must be running:

```
chrony.service   gpsd.service   ptp4l.service   phc2sys.service
```

## Setup

### 1. Install dependencies

```bash
cd ~/ClockMonitor
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> `gps` and `Jinja2` are inherited from system site-packages and are intentionally absent from `requirements.txt`.

### 2. Configure chrony (once)

Add to `/etc/chrony/chrony.conf` to enable NTP server statistics from localhost:

```
cmdallow 127.0.0.1
bindcmdaddress 127.0.0.1
```

```bash
sudo systemctl restart chrony
```

### 3. Configure sudo (once)

Required for `serverstats` and `clients` commands, which need root access to the chrony command socket:

```bash
echo "$USER ALL=(root) NOPASSWD: /usr/bin/chronyc" | sudo tee /etc/sudoers.d/clockmonitor
```

### 4. Smoke test

```bash
source .venv/bin/activate
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080
```

Open `http://<Pi-IP>:8080/` and verify all sections populate within a few seconds.

### 5. Install as systemd service

```bash
sed "s/YOUR_USER/$USER/g" clockmonitor.service | sudo tee /etc/systemd/system/clockmonitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now clockmonitor
```

## Access

```
http://<Pi-IP>:8080/
```

LAN-only. No authentication. Do not expose to the public internet.

## API

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/health` | Liveness probe — `{"ok": true}` |
| `GET /api/status` | Current snapshot from all sources (JSON) |
| `GET /api/history?source=<name>&minutes=<1-60>` | Time-series data |
| `GET /api/stream` | SSE stream of snapshots (~1 s interval) |

Valid `source` values: `chrony_offset` / `ptp_offset_from_master` / `gps_sat_used` / `gps_sat_visible` / `pps0_seq`

## Troubleshooting

**Service won't start**
```bash
journalctl -u clockmonitor -n 50
```

**chrony section shows red**
```bash
chronyc tracking    # verify chrony is running
chronyc sources     # check that PPS has state *
```

**GPS source shows `x` (amber) — this is normal**
The NMEA serial path introduces ~360 ms latency, so the GPS SHM source is always rejected as a falseticker. PPS provides the actual sub-µs lock. As long as PPS is selected (`*`), the system is operating correctly.

**NTP Server section shows no data**
```bash
sudo chronyc serverstats    # if 501, check chrony.conf and sudoers
```

**PTP section shows `data_source: journal`**
`/var/run/ptp4lro` is inaccessible. Add `uds_ro_address /var/run/ptp4lro` under `[global]` in `/etc/linuxptp/ptp4l.conf` and restart ptp4l.

**gpsd not responding**
```bash
systemctl status gpsd
cat /etc/default/gpsd    # confirm /dev/ttyAMA0 is listed in DEVICES
```
