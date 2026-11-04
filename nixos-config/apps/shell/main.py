"""Homy shell — connects the Rive HMI to the rest of the system.

The drawing is done by homy-hmi (apps/hmi, Rive's native renderer); this
process only drives it over its stdin/stdout. One homy-hmi plays homy-neo-hmi,
the whole screen in one file: top bar, sidebar, bottom bar, and the app area
the apps are tiled over (Qtile keeps the HMI window below them).

  homy-hmi → here    "number topbar/activeIndex 1"   a button was tapped
  here → homy-hmi    "number sidebar/activeIndex 2"  highlight the current group
                     "string bottombar/time 12:34"   the clock
                     "color Theme/accent #…"         theme tokens (homy-theme)

and connects it to the system: taps switch Qtile groups, Qtile reports group
changes to 127.0.0.1:47811/group?name=… (its setgroup hook), colours follow
the homy-theme service (127.0.0.1:47820/events).
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

UI = Path(os.environ.get("HOMY_UI_DIR", "/run/current-system/sw/share/homy/ui"))
HMI = os.environ.get("HOMY_HMI", "homy-hmi")
PORT = 47811                      # Qtile's setgroup hook talks to this
THEME_EVENTS = "http://127.0.0.1:47820/events"

# The HMI window. Qtile pins it by its title over the whole screen; "layout"
# fits the artboard to the screen (bars keep their size, the app area grows).
RIV, ARTBOARD, TITLE = "homy-neo-hmi", "HMI", "Homy HMI"

# Navigation per bar: activeIndex (button position) → what a tap does.
#   group name  switch to that Qtile group (the button stays highlighted there)
#   "power"     systemctl poweroff (sidebar button 4, like the old Shutdown button)
NAV = {
    "sidebar":   {0: "1", 1: "2", 2: "3", 3: "4", 4: "power"},
    "topbar":    {0: "5", 1: "9", 2: "8"},        # terminal, app menu, Wi-Fi
    "bottombar": {0: "7", 1: "6"},                # Bluetooth, system
}
MENU = ("topbar", 1)              # also highlighted while a launcher app (app:<id>) is shown


def log(msg: str):
    print(f"[homy-shell] {msg}", flush=True)


def active_index(bar: str, group: str) -> int:
    """The button to highlight on a bar while `group` is shown (-1: none)."""
    if group.startswith("app:") and bar == MENU[0]:
        return MENU[1]
    for index, action in NAV[bar].items():
        if action == group:
            return index
    return -1


def navigate(bar: str, index: int):
    """A button on a bar was tapped."""
    action = NAV[bar].get(index)
    if action == "power":
        log("power button → systemctl poweroff")
        subprocess.run(["systemctl", "poweroff"])
    elif action:
        subprocess.run(["qtile", "cmd-obj", "-o", "group", action, "-f", "toscreen"], capture_output=True)
    elif index >= 0:
        log(f"no action for {bar} button {index}")


class Hmi:
    """The homy-hmi process; restarted if it exits."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.group = "1"                              # Qtile starts on group 1 = Home
        self.index = {bar: active_index(bar, self.group) for bar in NAV}
        self.theme: dict[str, str] = {}

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._clock, daemon=True).start()

    def send(self, line: str):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(line + "\n")
                    self.proc.stdin.flush()
                except OSError:
                    pass

    def show_group(self, group: str):
        """Qtile switched groups: highlight the matching button on every bar."""
        self.group = group
        for bar in NAV:
            self.index[bar] = active_index(bar, group)
            self.send(f"number {bar}/activeIndex {self.index[bar]}")

    def set_theme(self, tokens: dict[str, str]):
        self.theme = tokens
        for name, hex_ in tokens.items():
            self.send(f"color Theme/{name} {hex_}")
        if "wallpaper" in tokens:
            self.send(f"background {tokens['wallpaper'][:7]}")

    def _clock(self):
        while True:
            self.send(f"string bottombar/time {time.strftime('%H:%M')}")
            time.sleep(60 - time.time() % 60 + 0.05)  # just after the next full minute

    def _run(self):
        cmd = [HMI, "--riv", str(UI / "riv" / f"{RIV}.riv"), "--artboard", ARTBOARD,
               "--title", TITLE, "--size", "1024x600", "--fit", "layout"]
        while True:
            started = time.monotonic()
            with self.lock:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             text=True, bufsize=1)
            for line in self.proc.stdout:
                self._handle(line.strip())
            log(f"homy-hmi exited ({self.proc.wait()})")
            # restart, but not in a tight loop if it can't start at all
            time.sleep(1 if time.monotonic() - started > 10 else 10)

    def _handle(self, line: str):
        kind, _, rest = line.partition(" ")
        if kind == "ready":
            log(f"ready ({rest})")
            for bar in NAV:
                self.send(f"watch {bar}/activeIndex")
            self.show_group(self.group)
            self.set_theme(self.theme)
            self.send(f"string bottombar/time {time.strftime('%H:%M')}")
            return
        path, _, value = rest.partition(" ")
        bar, _, prop = path.partition("/")
        if kind == "number" and bar in NAV and prop == "activeIndex":
            index = int(float(value))
            if index != self.index[bar]:
                self.index[bar] = index
                threading.Thread(target=navigate, args=(bar, index), daemon=True).start()
        else:
            log(line)


def follow_theme(hmi: Hmi):
    """Server-Sent Events from homy-theme: the active theme now and on change."""
    while True:
        try:
            with urllib.request.urlopen(THEME_EVENTS) as events:
                for raw in events:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        theme = json.loads(line[6:])
                        log(f"theme: {theme['id']}")
                        hmi.set_theme(theme["tokens"])
        except Exception as e:
            log(f"theme service unavailable ({e}); retrying")
        time.sleep(3)


def main():
    hmi = Hmi()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != "/group":
                self.send_error(404)
                return
            group = urllib.parse.parse_qs(url.query).get("name", [""])[0]
            self.send_response(204)
            self.end_headers()
            hmi.show_group(group)

        def log_message(self, *args):
            pass

    # One shell per session: the fixed port doubles as the lock.
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        log(f"port {PORT} in use — the shell is already running")
        raise SystemExit(0)

    hmi.start()
    threading.Thread(target=follow_theme, args=(hmi,), daemon=True).start()
    log(f"HMI: {RIV}.riv (homy-hmi)")
    server.serve_forever()


if __name__ == "__main__":
    main()
