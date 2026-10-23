"""NetworkManager access via nmcli. All functions block — call from a worker thread."""
from __future__ import annotations
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    ssid: str
    signal: int        # 0–100
    security: str      # e.g. "WPA2", "" for open networks
    in_use: bool
    saved_as: str      # connection profile name if saved, else ""

    @property
    def secure(self) -> bool:
        return bool(self.security) and self.security != "--"


@dataclass(frozen=True)
class WifiState:
    device: str | None         # e.g. "wlan0"; None = no Wi-Fi adapter
    radio_on: bool
    networks: tuple[Network, ...]
    ip: str                    # IPv4 of the Wi-Fi device, "" if none


def _nmcli(*args: str, timeout: float = 15) -> tuple[bool, str]:
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout if r.returncode == 0 else r.stderr).strip()


def _fields(line: str) -> list[str]:
    """Split one line of `nmcli -t` output (':' separated, '\\:' escaped)."""
    fields, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            fields.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    fields.append(cur)
    return fields


def _wifi_device() -> str | None:
    ok, out = _nmcli("-t", "-f", "DEVICE,TYPE", "device")
    for line in out.splitlines() if ok else []:
        dev, typ = (_fields(line) + ["", ""])[:2]
        if typ == "wifi":
            return dev
    return None


def _saved_profiles() -> dict[str, str]:
    """SSID -> connection profile name for saved Wi-Fi networks."""
    ok, out = _nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
    profiles = {}
    for line in out.splitlines() if ok else []:
        name, typ = (_fields(line) + ["", ""])[:2]
        if typ != "802-11-wireless":
            continue
        ok, ssid = _nmcli("-g", "802-11-wireless.ssid", "connection", "show", name)
        profiles[ssid if ok and ssid else name] = name
    return profiles


def state() -> WifiState:
    dev = _wifi_device()
    if dev is None:
        return WifiState(None, False, (), "")
    ok, radio = _nmcli("radio", "wifi")
    radio_on = ok and radio == "enabled"

    saved = _saved_profiles()
    best: dict[str, Network] = {}           # strongest access point per SSID
    ok, out = _nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no")
    for line in out.splitlines() if ok else []:
        in_use, ssid, signal, security = (_fields(line) + ["", "", "", ""])[:4]
        if not ssid:
            continue                        # hidden network
        net = Network(ssid, int(signal or 0), security, in_use == "*", saved.get(ssid, ""))
        cur = best.get(ssid)
        if cur is None or net.in_use or (not cur.in_use and net.signal > cur.signal):
            best[ssid] = net

    ok, ip = _nmcli("-g", "IP4.ADDRESS", "device", "show", dev)
    ip = ip.split("|")[0].split("/")[0] if ok else ""
    nets = sorted(best.values(), key=lambda n: (not n.in_use, -n.signal))
    return WifiState(dev, radio_on, tuple(nets), ip)


# ── Actions — each returns (ok, message) ─────────────────────────────────────

def rescan() -> tuple[bool, str]:
    return _nmcli("device", "wifi", "rescan")


def set_radio(on: bool) -> tuple[bool, str]:
    return _nmcli("radio", "wifi", "on" if on else "off")


def connect_saved(profile: str) -> tuple[bool, str]:
    return _nmcli("connection", "up", "id", profile, timeout=45)


def connect_new(ssid: str, password: str | None) -> tuple[bool, str]:
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    ok, msg = _nmcli(*args, timeout=45)
    if not ok:
        # A failed attempt (e.g. wrong password) still leaves a profile behind;
        # remove it so the next try starts clean instead of reusing bad secrets.
        _nmcli("connection", "delete", "id", ssid)
    return ok, msg


def disconnect(device: str) -> tuple[bool, str]:
    return _nmcli("device", "disconnect", device)


def forget(profile: str) -> tuple[bool, str]:
    return _nmcli("connection", "delete", "id", profile)
