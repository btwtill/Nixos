"""Data collection — systemd units, our apps, and resource usage.

Everything here is blocking and is called from the background poller thread
in main.py, never from the Qt thread.
"""
from __future__ import annotations
import os
import subprocess
import time
from dataclasses import dataclass, field

import psutil


# ── Services ──────────────────────────────────────────────────────────────────

@dataclass
class UnitStatus:
    unit: str
    label: str
    active: str          # active / inactive / failed / activating / not-found
    sub: str             # running / exited / dead / ...
    description: str = ""
    user: bool = False


@dataclass
class ServicesSnapshot:
    watched: list[UnitStatus]
    other_running: list[UnitStatus]
    failed: list[UnitStatus]
    apps: list["AppStatus"] = field(default_factory=list)


def _systemctl(args: list[str], user: bool = False) -> str:
    cmd = ["systemctl", *(["--user"] if user else []), "--no-pager", *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _show_units(services: list[dict], user: bool) -> list[UnitStatus]:
    if not services:
        return []
    out = _systemctl(
        ["show", "--property=LoadState,ActiveState,SubState,Description",
         *[s["unit"] for s in services]],
        user,
    )
    # One block of KEY=VALUE lines per unit, in request order, blank-line separated.
    blocks = [b for b in out.strip().split("\n\n")] if out.strip() else []
    result = []
    for i, svc in enumerate(services):
        props = {}
        if i < len(blocks):
            for line in blocks[i].splitlines():
                key, _, value = line.partition("=")
                props[key] = value
        active = props.get("ActiveState", "unknown")
        if props.get("LoadState") == "not-found":
            active = "not-found"
        result.append(UnitStatus(
            unit=svc["unit"],
            label=svc.get("label", svc["unit"]),
            active=active,
            sub=props.get("SubState", ""),
            description=props.get("Description", ""),
            user=user,
        ))
    return result


def _list_units(state: str) -> list[UnitStatus]:
    out = _systemctl(["list-units", "--type=service", f"--state={state}",
                      "--no-legend", "--plain"])
    units = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, _load, active, sub = parts[:4]
        desc = parts[4] if len(parts) > 4 else ""
        units.append(UnitStatus(unit, unit.removesuffix(".service"), active, sub, desc))
    return units


def collect_services(services: list[dict]) -> ServicesSnapshot:
    system = [s for s in services if not s.get("user")]
    user   = [s for s in services if s.get("user")]
    by_unit = {(u.unit, u.user): u
               for u in _show_units(system, False) + _show_units(user, True)}
    watched = [by_unit[(s["unit"], bool(s.get("user")))] for s in services]

    watched_names = {s["unit"] for s in services}
    other = [u for u in _list_units("running") if u.unit not in watched_names]
    failed = _list_units("failed")
    return ServicesSnapshot(watched, other, failed)


# ── Apps + processes ──────────────────────────────────────────────────────────

@dataclass
class AppStatus:
    name: str
    running: bool
    pid: int | None = None
    cpu: float = 0.0       # % of one core
    rss: int = 0           # bytes


@dataclass
class ProcInfo:
    pid: int
    name: str
    cpu: float
    rss: int


class ProcessScanner:
    """Keeps psutil.Process objects alive between scans so cpu_percent()
    reports usage since the previous scan instead of 0.0."""

    def __init__(self):
        self._procs: dict[int, psutil.Process] = {}

    def scan(self, apps: list[str], top_n: int) -> tuple[list[AppStatus], list[ProcInfo]]:
        seen: dict[int, psutil.Process] = {}
        infos: list[tuple[ProcInfo, list[str]]] = []
        for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
            proc = self._procs.get(p.pid, p)
            try:
                cpu = proc.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            seen[p.pid] = proc
            mem = p.info.get("memory_info")
            infos.append((
                ProcInfo(p.pid, p.info.get("name") or "?", cpu, mem.rss if mem else 0),
                p.info.get("cmdline") or [],
            ))
        self._procs = seen

        app_status = []
        for app in apps:
            marker = f"/lib/{app}/main.py"
            match = next((pi for pi, cmd in infos if any(marker in c for c in cmd)), None)
            if match:
                app_status.append(AppStatus(app, True, match.pid, match.cpu, match.rss))
            else:
                app_status.append(AppStatus(app, False))

        top = sorted((pi for pi, _ in infos), key=lambda pi: pi.cpu, reverse=True)[:top_n]
        return app_status, top


# ── Resources ─────────────────────────────────────────────────────────────────

@dataclass
class ResourceSnapshot:
    cpu_percent: float
    per_core: list[float]
    cpu_freq_mhz: float | None
    mem_used: int
    mem_total: int
    swap_used: int
    swap_total: int
    disk_used: int
    disk_total: int
    temp_c: float | None
    load_avg: tuple[float, float, float]
    uptime_s: float
    net_rx_bps: float
    net_tx_bps: float
    top_procs: list[ProcInfo]


def _cpu_temp() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    # Pi: cpu_thermal; x86/ARM VMs usually expose nothing.
    for key in ("cpu_thermal", "coretemp", "k10temp", "soc_thermal"):
        if temps.get(key):
            return temps[key][0].current
    for entries in temps.values():
        if entries:
            return entries[0].current
    return None


class ResourceSampler:
    def __init__(self):
        self._last_net = psutil.net_io_counters()
        self._last_t = time.monotonic()
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)

    def sample(self, top_procs: list[ProcInfo]) -> ResourceSnapshot:
        now = time.monotonic()
        dt = max(now - self._last_t, 1e-3)
        net = psutil.net_io_counters()
        rx = (net.bytes_recv - self._last_net.bytes_recv) / dt
        tx = (net.bytes_sent - self._last_net.bytes_sent) / dt
        self._last_net, self._last_t = net, now

        try:
            freq = psutil.cpu_freq()
            freq_mhz = freq.current if freq else None
        except (OSError, NotImplementedError):
            freq_mhz = None

        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")

        return ResourceSnapshot(
            cpu_percent=psutil.cpu_percent(None),
            per_core=psutil.cpu_percent(None, percpu=True),
            cpu_freq_mhz=freq_mhz,
            mem_used=mem.total - mem.available,
            mem_total=mem.total,
            swap_used=swap.used,
            swap_total=swap.total,
            disk_used=disk.used,
            disk_total=disk.total,
            temp_c=_cpu_temp(),
            load_avg=os.getloadavg(),
            uptime_s=time.time() - psutil.boot_time(),
            net_rx_bps=max(rx, 0.0),
            net_tx_bps=max(tx, 0.0),
            top_procs=top_procs,
        )


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_uptime(s: float) -> str:
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
