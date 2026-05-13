// ─── Helpers ─────────────────────────────────────────────────────
const HEALTH_CLASS = { green: "pill-green", amber: "pill-amber", red: "pill-red" };

function pillClass(h) { return HEALTH_CLASS[h] || "pill-unknown"; }

function applyPill(el, health, label) {
  el.className = "pill " + pillClass(health);
  el.textContent = label || health || "–";
}

function fmtNs(s) {
  if (s === null || s === undefined) return "–";
  const ns = s * 1e9;
  const abs = Math.abs(ns);
  if (abs >= 1e6)  return (ns / 1e6).toFixed(3) + " ms";
  if (abs >= 1e3)  return (ns / 1e3).toFixed(3) + " µs";
  return ns.toFixed(1) + " ns";
}

function fmtNsDirect(ns) {
  if (ns === null || ns === undefined) return "–";
  const abs = Math.abs(ns);
  if (abs >= 1e6)  return (ns / 1e6).toFixed(3) + " ms";
  if (abs >= 1e3)  return (ns / 1e3).toFixed(3) + " µs";
  return ns.toFixed(1) + " ns";
}

function fmtPpm(v) { return v == null ? "–" : v.toFixed(4) + " ppm"; }
function fmtSec(v) { return v == null ? "–" : fmtNs(v); }

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? "–";
}

function setField(sel, val) {
  document.querySelectorAll(`[data-field="${sel}"]`).forEach(el => {
    el.textContent = val ?? "–";
  });
}

// ─── UTC clock ──────────────────────────────────────────────────
function tickClock() {
  const now = new Date();
  setText("utc-clock",
    now.toISOString().replace("T", " ").slice(0, 19) + " UTC");
}
tickClock();
setInterval(tickClock, 1000);

// ─── Charts ──────────────────────────────────────────────────────
const MAX_POINTS = 600;

function makeChart(id, label, color, unit) {
  const ctx = document.getElementById(id).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        label,
        data: [],
        borderColor: color,
        backgroundColor: color + "22",
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: "linear",
          ticks: {
            color: "#7d8590",
            maxTicksLimit: 6,
            callback: v => {
              const d = new Date(v * 1000);
              return d.toISOString().slice(11, 19);
            }
          },
          grid: { color: "#21262d" },
        },
        y: {
          ticks: { color: "#7d8590", callback: v => v.toFixed(1) + " " + unit },
          grid: { color: "#21262d" },
        }
      },
      plugins: { legend: { display: false } },
    }
  });
}

const chartChrony = makeChart("chart-chrony", "offset", "#58a6ff", "ns");
const chartPtp    = makeChart("chart-ptp",    "offset", "#bc8cff", "ns");
const chartGps    = makeChart("chart-gps",    "sats",   "#2ecc71", "");

function pushPoint(chart, t, v) {
  const ds = chart.data.datasets[0];
  ds.data.push({ x: t, y: v });
  if (ds.data.length > MAX_POINTS) ds.data.shift();
  chart.update("none");
}

// ─── History prefetch ────────────────────────────────────────────
async function prefetch() {
  const pairs = [
    ["chrony_offset", chartChrony, v => v * 1e9],
    ["ptp_offset_from_master", chartPtp, v => v],
    ["gps_sat_used", chartGps, v => v],
  ];
  for (const [src, chart, xform] of pairs) {
    try {
      const r = await fetch(`/api/history?source=${src}&minutes=10`);
      const d = await r.json();
      const ds = chart.data.datasets[0];
      ds.data = d.t.map((t, i) => ({ x: t, y: xform(d.v[i] ?? 0) }));
      chart.update("none");
    } catch (_) {}
  }
}
prefetch();

// ─── Source state helpers ────────────────────────────────────────
const STATE_CLASS = {
  "*": "src-selected",
  "+": "src-candidate",
  "x": "src-outlier",
  "~": "src-outlier",
  "-": "src-stale",
  "?": "src-stale",
};

function renderSources(sources) {
  const tbody = document.getElementById("chrony-sources-body");
  if (!tbody || !Array.isArray(sources)) return;
  tbody.innerHTML = "";
  for (const s of sources.filter(s => s.state !== "-" && s.state !== "?")) {
    const tr = document.createElement("tr");
    const stateClass = STATE_CLASS[s.state] || "";
    const offsetStr = fmtNs(s.last_sample_offset_s);
    tr.innerHTML = `
      <td class="src-state ${stateClass}">${s.mode || "?"}</td>
      <td class="src-state ${stateClass}">${s.state || "?"}</td>
      <td>${s.name || "?"}</td>
      <td>${s.stratum ?? "?"}</td>
      <td class="${stateClass}">${offsetStr}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ─── NTP Server ──────────────────────────────────────────────────
function renderNtpServer(chrony) {
  const ss = chrony.serverstats || {};
  setText("ntp-rx",          ss.ntp_packets_received   ?? "–");
  setText("ntp-drop",        ss.ntp_packets_dropped     ?? "–");
  setText("ntp-cmd-rx",      ss.command_packets_received ?? "–");
  setText("ntp-interleaved", ss.interleaved_ntp_packets ?? "–");
  setText("ntp-hw-tx",       ss.ntp_hardware_tx_timestamps ?? "–");

  const tbody = document.getElementById("ntp-clients-body");
  if (!tbody) return;
  const clients = (chrony.clients || []).filter(c => c.hostname !== "localhost" || c.ntp_rx > 0);
  if (!clients.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);padding:4px 6px">No NTP clients yet</td></tr>';
    return;
  }
  tbody.innerHTML = "";
  for (const c of clients) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${c.hostname}</td><td>${c.ntp_rx}</td><td>${c.ntp_drop}</td><td>${c.last_ntp}</td>`;
    tbody.appendChild(tr);
  }
}

// ─── GPS mode labels ─────────────────────────────────────────────
const GPS_MODE = { 0: "No data", 1: "No fix", 2: "2D fix", 3: "3D fix" };

// ─── PPS devices ─────────────────────────────────────────────────
function renderPps(pps, health) {
  const container = document.getElementById("pps-devices");
  if (!container) return;
  const devices = pps.devices || {};
  if (!Object.keys(devices).length) {
    container.innerHTML = '<span style="color:var(--muted)">No PPS devices</span>';
    return;
  }
  container.innerHTML = "";
  for (const [name, d] of Object.entries(devices)) {
    const hz = d.hz != null ? d.hz.toFixed(3) + " Hz" : "–";
    const age = d.last_assert_epoch
      ? ((Date.now() / 1000 - d.last_assert_epoch)).toFixed(1) + "s ago"
      : "–";
    const div = document.createElement("div");
    div.className = "pps-device";
    div.innerHTML = `
      <div class="name">${name}</div>
      <div class="hz">${hz}</div>
      <div style="font-size:11px;color:var(--muted)">seq ${d.seq ?? "–"} · ${age}</div>
    `;
    container.appendChild(div);
  }
}

// ─── Services ────────────────────────────────────────────────────
function renderServices(services) {
  const row = document.getElementById("services-row");
  if (!row) return;
  row.innerHTML = "";
  for (const [name, state] of Object.entries(services)) {
    const dotClass = state === "active" ? "active"
      : state === "failed" ? "failed"
      : state === "inactive" ? "inactive"
      : "unknown";
    const pill = document.createElement("div");
    pill.className = "svc-pill";
    pill.innerHTML = `<span class="svc-dot ${dotClass}"></span><span>${name}</span><span style="color:var(--muted);font-size:11px">${state}</span>`;
    row.appendChild(pill);
  }
}

// ─── Main update ─────────────────────────────────────────────────
function applySnapshot(snap) {
  const h = snap.health || {};
  const oh = snap.overall_health || "amber";

  // Overall
  const opill = document.getElementById("overall-pill");
  if (opill) applyPill(opill, oh, oh.toUpperCase());

  // Chrony
  const c = snap.chrony || {};
  applyPill(document.getElementById("chrony-pill"), h.chrony, h.chrony);

  const bigOffset = document.getElementById("chrony-offset-big");
  if (bigOffset) {
    bigOffset.textContent = fmtNs(c.last_offset_s);
    bigOffset.className = "big-val " + (h.chrony || "amber");
  }

  setField("chrony.stratum", c.stratum ?? "–");
  setField("chrony.ref_id", c.ref_name ? `${c.ref_name} (${c.ref_id || ""})` : (c.ref_id || "–"));
  setField("chrony.rms_offset_s", fmtNs(c.rms_offset_s));
  setField("chrony.frequency_ppm", fmtPpm(c.frequency_ppm));
  setField("chrony.skew_ppm", fmtPpm(c.skew_ppm));
  setField("chrony.root_delay_s", fmtNs(c.root_delay_s));
  setField("chrony.root_dispersion_s", fmtNs(c.root_dispersion_s));
  setField("chrony.leap_status", c.leap_status ?? "–");
  renderSources(c.sources);
  renderNtpServer(c);

  if (c.last_offset_s != null && snap.now) {
    pushPoint(chartChrony, snap.now, c.last_offset_s * 1e9);
  }

  // GPS
  const g = snap.gpsd || {};
  applyPill(document.getElementById("gps-pill"), h.gpsd, h.gpsd);

  const modeLabel = GPS_MODE[g.mode] || `mode ${g.mode}`;
  const modeBig = document.getElementById("gps-mode-big");
  if (modeBig) {
    modeBig.textContent = modeLabel;
    modeBig.className = "big-val " + (h.gpsd || "amber");
    modeBig.style.fontSize = "22px";
  }
  setText("gps-sats-used", g.sats_used ?? "–");
  setText("gps-sats-visible", g.sats_visible ?? "–");
  setText("gps-lat", g.lat != null ? g.lat.toFixed(7) + "°" : "–");
  setText("gps-lon", g.lon != null ? g.lon.toFixed(7) + "°" : "–");
  setText("gps-alt", g.alt_m != null ? g.alt_m.toFixed(1) + " m" : "–");
  setText("gps-time", g.time ?? "–");
  setText("gps-ep", (g.epx != null && g.epy != null) ? `±${g.epx.toFixed(2)} / ±${g.epy.toFixed(2)} m` : "–");

  if (g.sats_used != null && snap.now) {
    pushPoint(chartGps, snap.now, g.sats_used);
  }

  // PTP
  const p = snap.ptp4l || {};
  applyPill(document.getElementById("ptp-pill"), h.ptp4l, h.ptp4l);

  const ptpBig = document.getElementById("ptp-offset-big");
  if (ptpBig) {
    ptpBig.textContent = fmtNsDirect(p.offset_from_master_ns);
    ptpBig.className = "big-val " + (h.ptp4l || "amber");
  }
  setText("ptp-port-state", p.port_state || "–");
  setText("ptp-delay", fmtNsDirect(p.mean_path_delay_ns));
  setField("ptp4l.steps_removed", p.steps_removed ?? "–");
  setField("ptp4l.port_identity", p.port_identity || "–");

  const srcBadge = document.getElementById("ptp-source-badge");
  if (srcBadge) srcBadge.style.display = (p.data_source === "journal") ? "inline" : "none";

  if (p.offset_from_master_ns != null && snap.now) {
    pushPoint(chartPtp, snap.now, p.offset_from_master_ns);
  }

  // PPS
  applyPill(document.getElementById("pps-pill"), h.pps, h.pps);
  renderPps(snap.pps || {}, h.pps);

  // Services
  applyPill(document.getElementById("svc-pill"), h.systemd, h.systemd);
  const sd = snap.systemd || {};
  renderServices(sd.services || {});
}

// ─── SSE ──────────────────────────────────────────────────────────
const banner = document.getElementById("disconnected-banner");
let es;

function connect() {
  es = new EventSource("/api/stream");

  es.addEventListener("snapshot", e => {
    banner.style.display = "none";
    try {
      applySnapshot(JSON.parse(e.data));
    } catch (_) {}
  });

  es.onerror = () => {
    banner.style.display = "block";
  };

  es.onopen = () => {
    banner.style.display = "none";
  };
}

connect();
