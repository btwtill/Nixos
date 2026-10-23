"""BlueZ access: device list via one D-Bus call (busctl), actions via bluetoothctl.

All functions block — call them from a worker thread.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass

PAIR_TIMEOUT_S = 40


@dataclass(frozen=True)
class Adapter:
    path: str
    name: str
    powered: bool
    discovering: bool


@dataclass(frozen=True)
class Device:
    address: str
    name: str
    paired: bool
    connected: bool
    trusted: bool
    rssi: int | None
    icon: str          # BlueZ icon hint: audio-headset, phone, input-mouse, …


def _run(*cmd: str, timeout: float = 10) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (r.stdout + r.stderr).strip()
    # bluetoothctl reports most failures in its output, not the exit code.
    failed = r.returncode != 0 or "Failed" in out or "not available" in out
    return not failed, out


def snapshot() -> tuple[Adapter | None, list[Device]]:
    """The first adapter and every device BlueZ currently knows about."""
    ok, out = _run("busctl", "--json=short", "call", "org.bluez", "/",
                   "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    if not ok:
        return None, []
    try:
        objects = json.loads(out)["data"][0]
    except (ValueError, KeyError, IndexError):
        return None, []

    def prop(props: dict, key: str, default=None):
        return props.get(key, {}).get("data", default)

    adapter = None
    devices = []
    for path, ifaces in sorted(objects.items()):
        if "org.bluez.Adapter1" in ifaces and adapter is None:
            a = ifaces["org.bluez.Adapter1"]
            adapter = Adapter(path, prop(a, "Alias", "") or prop(a, "Name", ""),
                              bool(prop(a, "Powered", False)), bool(prop(a, "Discovering", False)))
        elif "org.bluez.Device1" in ifaces:
            d = ifaces["org.bluez.Device1"]
            devices.append(Device(
                address=prop(d, "Address", ""),
                name=prop(d, "Name", "") or "",        # Alias falls back to the address
                paired=bool(prop(d, "Paired", False)),
                connected=bool(prop(d, "Connected", False)),
                trusted=bool(prop(d, "Trusted", False)),
                rssi=prop(d, "RSSI"),
                icon=prop(d, "Icon", "") or "",
            ))
    return adapter, devices


# ── Actions — each returns (ok, message) ─────────────────────────────────────

def set_power(on: bool) -> tuple[bool, str]:
    return _run("bluetoothctl", "power", "on" if on else "off")


def scan(seconds: int) -> tuple[bool, str]:
    """Discover classic (speakers, headphones, phones) and LE devices."""
    return _run("bluetoothctl", "--timeout", str(seconds), "scan", "on", timeout=seconds + 10)


def pair_and_connect(address: str) -> tuple[bool, str]:
    ok, out = _run("bluetoothctl", "--agent", "NoInputNoOutput", "pair", address,
                   timeout=PAIR_TIMEOUT_S)
    if not ok and "AlreadyExists" not in out:
        return False, _last_line(out)
    _run("bluetoothctl", "trust", address)
    return connect(address)


def connect(address: str) -> tuple[bool, str]:
    ok, out = _run("bluetoothctl", "connect", address, timeout=PAIR_TIMEOUT_S)
    return ok, _last_line(out)


def disconnect(address: str) -> tuple[bool, str]:
    ok, out = _run("bluetoothctl", "disconnect", address)
    return ok, _last_line(out)


def forget(address: str) -> tuple[bool, str]:
    ok, out = _run("bluetoothctl", "remove", address)
    return ok, _last_line(out)


def _last_line(out: str) -> str:
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else ""
