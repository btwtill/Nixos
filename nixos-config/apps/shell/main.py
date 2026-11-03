"""Homy shell — connects the Rive HMI to the rest of the system.

The drawing is done by homy-hmi (apps/hmi, Rive's native renderer on OpenGL
ES); this process only drives it, one homy-hmi per surface, over its
stdin/stdout:

  homy-hmi → here    "number activeIndex 2"   a button was tapped
  here → homy-hmi    "number activeIndex 2"   highlight the button of the group
                     "color Theme/accent #…"  theme tokens (homy-theme)

and connects it to the system: taps switch Qtile groups, Qtile reports group
changes to 127.0.0.1:47811/group?name=… (its setgroup hook), colours follow
the homy-theme service (127.0.0.1:47820/events).

  sidebar    right edge. Qtile pins the window by its title.

    homy-shell [surface …]      default: all surfaces
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

UI = Path(os.environ.get("HOMY_UI_DIR", "/run/current-system/sw/share/homy/ui"))
HMI = os.environ.get("HOMY_HMI", "homy-hmi")
PORT = 47811                      # Qtile's setgroup hook talks to this
THEME_EVENTS = "http://127.0.0.1:47820/events"

# surface → the homy-hmi window for it. Qtile pins windows by title.
SURFACES = {
    "sidebar": {"riv": "sidebar", "artboard": "SideBar", "title": "Homy Sidebar",
                "size": "180x520", "fit": "contain", "align": "topCenter"},
}

# Navigation: activeIndex (button position) → what a tap does.
#   group name  switch to that Qtile group (and highlight the button there)
#   "power"     systemctl poweroff (sidebar button 4, like the old Shutdown button)
NAV = {
    "sidebar": {0: "1", 1: "2", 2: "3", 3: "4", 4: "power"},
}


def log(msg: str):
    print(f"[homy-shell] {msg}", flush=True)


def active_index(surface: str, group: str) -> int:
    """The button to highlight on a surface while `group` is shown (-1: none)."""
    for index, action in NAV.get(surface, {}).items():
        if action == group:
            return index
    return -1


def navigate(surface: str, index: int):
    """A button on a surface was tapped."""
    action = NAV.get(surface, {}).get(index)
    if action == "power":
        log("power button → systemctl poweroff")
        subprocess.run(["systemctl", "poweroff"])
    elif action:
        subprocess.run(["qtile", "cmd-obj", "-o", "group", action, "-f", "toscreen"], capture_output=True)
    elif index >= 0:
        log(f"no action for {surface} button {index}")


class Surface:
    """One homy-hmi process; restarted if it exits."""

    def __init__(self, name: str, spec: dict):
        self.name, self.spec = name, spec
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.index = active_index(name, "1")          # Qtile starts on group 1 = Home
        self.theme: dict[str, str] = {}

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, line: str):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(line + "\n")
                    self.proc.stdin.flush()
                except OSError:
                    pass

    def set_active(self, index: int):
        self.index = index
        self.send(f"number activeIndex {index}")

    def set_theme(self, tokens: dict[str, str]):
        self.theme = tokens
        for name, hex_ in tokens.items():
            self.send(f"color Theme/{name} {hex_}")
        if "wallpaper" in tokens:
            self.send(f"background {tokens['wallpaper'][:7]}")

    def _run(self):
        s = self.spec
        cmd = [HMI, "--riv", str(UI / "riv" / f"{s['riv']}.riv"), "--artboard", s["artboard"],
               "--title", s["title"], "--size", s["size"], "--fit", s["fit"], "--align", s["align"]]
        while True:
            started = time.monotonic()
            with self.lock:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             text=True, bufsize=1)
            for line in self.proc.stdout:
                self._handle(line.strip())
            log(f"{self.name}: homy-hmi exited ({self.proc.wait()})")
            # restart, but not in a tight loop if it can't start at all
            time.sleep(1 if time.monotonic() - started > 10 else 10)

    def _handle(self, line: str):
        kind, _, rest = line.partition(" ")
        if kind == "ready":
            log(f"{self.name}: ready ({rest})")
            self.send("watch activeIndex")
            self.set_active(self.index)
            self.set_theme(self.theme)
        elif kind == "number" and rest.startswith("activeIndex "):
            index = int(float(rest.split()[1]))
            if index != self.index:
                self.index = index
                threading.Thread(target=navigate, args=(self.name, index), daemon=True).start()
        else:
            log(f"{self.name}: {line}")


def follow_theme(surfaces: list[Surface]):
    """Server-Sent Events from homy-theme: the active theme now and on change."""
    while True:
        try:
            with urllib.request.urlopen(THEME_EVENTS) as events:
                for raw in events:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        theme = json.loads(line[6:])
                        log(f"theme: {theme['id']}")
                        for s in surfaces:
                            s.set_theme(theme["tokens"])
        except Exception as e:
            log(f"theme service unavailable ({e}); retrying")
        time.sleep(3)


def main():
    wanted = sys.argv[1:] or list(SURFACES)
    unknown = [s for s in wanted if s not in SURFACES]
    if unknown:
        sys.exit(f"homy-shell: unknown surface(s) {unknown}; known: {list(SURFACES)}")
    surfaces = [Surface(name, SURFACES[name]) for name in wanted]

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != "/group":
                self.send_error(404)
                return
            group = urllib.parse.parse_qs(url.query).get("name", [""])[0]
            self.send_response(204)
            self.end_headers()
            for s in surfaces:
                s.set_active(active_index(s.name, group))

        def log_message(self, *args):
            pass

    # One shell per session: the fixed port doubles as the lock.
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        log(f"port {PORT} in use — the shell is already running")
        sys.exit(0)

    for s in surfaces:
        s.start()
    threading.Thread(target=follow_theme, args=(surfaces,), daemon=True).start()
    log(f"surfaces: {', '.join(wanted)} (homy-hmi)")
    server.serve_forever()


if __name__ == "__main__":
    main()
