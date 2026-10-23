"""AirPlay (shairport-sync) now-playing state and remote control over MPRIS.

Shared by the music and home apps (copied next to each app's main.py by its
default.nix). MPRIS is used instead of the metadata pipe because a pipe can
only be read by one app; any number of apps can query MPRIS.

Requires shairport-sync on the *session* bus
(general.mpris_service_bus = "session" in the host config). Uses the busctl /
wpctl command-line tools, so no Python D-Bus bindings are needed.
"""
from __future__ import annotations
import json
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Optional

BUS_NAME = "org.mpris.MediaPlayer2.ShairportSync"
OBJ_PATH = "/org/mpris/MediaPlayer2"
PLAYER   = "org.mpris.MediaPlayer2.Player"

POLL_S = 1.0


@dataclass
class TrackInfo:
    title:   str = ""
    artist:  str = ""
    album:   str = ""
    playing: bool = False
    art:     Optional[bytes] = field(default=None, repr=False)
    art_url: str = ""

    def key(self) -> tuple:
        """Everything that matters for a redraw (art compared by URL)."""
        return (self.title, self.artist, self.album, self.playing, self.art_url)


def _run(*cmd: str) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _busctl(*args: str) -> Optional[str]:
    return _run("busctl", "--user", "--json=short", *args)


def _variant_str(meta: dict, key: str) -> str:
    value = meta.get(key, {}).get("data")
    if isinstance(value, list):                 # xesam:artist is a string list
        value = ", ".join(str(v) for v in value)
    return str(value) if value else ""


def read_state() -> Optional[TrackInfo]:
    """Current track, or None if shairport-sync is not on the session bus."""
    out = _busctl("get-property", BUS_NAME, OBJ_PATH, PLAYER, "Metadata", "PlaybackStatus")
    if not out:
        return None
    try:
        meta, status = (json.loads(line) for line in out.splitlines() if line.strip())
    except ValueError:
        return None
    meta = meta.get("data") or {}
    return TrackInfo(
        title=_variant_str(meta, "xesam:title"),
        artist=_variant_str(meta, "xesam:artist"),
        album=_variant_str(meta, "xesam:album"),
        playing=status.get("data") == "Playing",
        art_url=_variant_str(meta, "mpris:artUrl"),
    )


def _load_art(url: str) -> Optional[bytes]:
    if not url.startswith("file://"):
        return None
    try:
        with open(urllib.parse.unquote(url[len("file://"):]), "rb") as f:
            return f.read()
    except OSError:
        return None


class AirPlayWatcher(threading.Thread):
    """Polls MPRIS and calls on_update(TrackInfo) from this background thread
    whenever something changes. Callers must marshal to the Qt thread (emit a
    signal from the callback)."""

    def __init__(self, on_update: Callable[[TrackInfo], None]):
        super().__init__(daemon=True)
        self._on_update = on_update
        self._last_key: tuple | None = None
        self._art_cache: tuple[str, Optional[bytes]] = ("", None)

    def run(self):
        while True:
            info = read_state() or TrackInfo()
            if info.key() != self._last_key:
                self._last_key = info.key()
                if info.art_url != self._art_cache[0]:
                    self._art_cache = (info.art_url, _load_art(info.art_url))
                info.art = self._art_cache[1]
                self._on_update(info)
            time.sleep(POLL_S)


# ── Remote control ────────────────────────────────────────────────────────────
# shairport forwards these to the sending iPhone/Mac via DACP. Blocking —
# call from a worker thread.

def _player(method: str):
    _run("busctl", "--user", "call", BUS_NAME, OBJ_PATH, PLAYER, method)


def play_pause():  _player("PlayPause")
def next_track():  _player("Next")
def prev_track():  _player("Previous")

# Volume of the local output (where the AirPlay audio is played).
def volume_up():   _run("wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+")
def volume_down(): _run("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-")


ACTIONS: dict[str, Callable[[], None]] = {
    "play_pause":  play_pause,
    "next":        next_track,
    "prev":        prev_track,
    "volume_up":   volume_up,
    "volume_down": volume_down,
}


def run_action(action: str):
    """Run a control action in a background thread (never blocks the UI)."""
    fn = ACTIONS.get(action)
    if fn:
        threading.Thread(target=fn, daemon=True).start()
