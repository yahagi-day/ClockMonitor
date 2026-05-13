from typing import Literal
from pydantic import BaseModel


class ChronySource(BaseModel):
    mode: str
    state: str
    name: str
    stratum: int
    poll: int
    reach: str
    last_rx_s: float
    last_sample_offset_s: float
    last_sample_err_s: float


class ChronySnapshot(BaseModel):
    ref_id: str = ""
    ref_name: str = ""
    stratum: int = 0
    ref_time_epoch: float = 0.0
    system_time_offset_s: float = 0.0
    last_offset_s: float = 0.0
    rms_offset_s: float = 0.0
    frequency_ppm: float = 0.0
    residual_freq_ppm: float = 0.0
    skew_ppm: float = 0.0
    root_delay_s: float = 0.0
    root_dispersion_s: float = 0.0
    update_interval_s: float = 0.0
    leap_status: str = ""
    selected_source: str = ""
    sources: list[ChronySource] = []


class GpsSnapshot(BaseModel):
    mode: int = 0
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    time: str | None = None
    epx: float | None = None
    epy: float | None = None
    ept: float | None = None
    sats_used: int = 0
    sats_visible: int = 0


class Ptp4lSnapshot(BaseModel):
    port_state: str = ""
    offset_from_master_ns: float = 0.0
    mean_path_delay_ns: float = 0.0
    steps_removed: int = 0
    domain: int = 0
    port_identity: str = ""
    data_source: Literal["pmc", "journal", "error"] = "error"


class PpsDeviceSnapshot(BaseModel):
    seq: int = 0
    last_assert_epoch: float = 0.0
    hz: float | None = None


class PpsSnapshot(BaseModel):
    devices: dict[str, PpsDeviceSnapshot] = {}


class SystemdSnapshot(BaseModel):
    services: dict[str, str] = {}


class StatusResponse(BaseModel):
    now: float
    health: dict[str, str]
    overall_health: str
    chrony: dict
    gpsd: dict
    ptp4l: dict
    pps: dict
    systemd: dict


class HistoryResponse(BaseModel):
    name: str
    t: list[float]
    v: list[float | None]
