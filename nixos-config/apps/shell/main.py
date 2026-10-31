"""Homy shell — the Rive-drawn parts of the desktop, in one process.

Every surface (sidebar, top bar, wallpaper, later the bottom bar) is a frameless QtWebEngine
window playing one artboard of a .riv from the homy-ui package (HOMY_UI_DIR,
set by the wrapper). They share one Chromium (browser, GPU and renderer
processes), so a surface costs a page, not a whole browser. Qtile recognises
the windows by title and pins them (dotfiles/qtile/config.py, "Homy shell").

  sidebar    right edge, transparent. Tap → switch the Qtile group; Qtile
             reports group changes to 127.0.0.1:47811/group?name=… → highlight.
  topbar     top edge, full width, transparent. Terminal / app menu / Wi-Fi,
             same tap + highlight scheme as the sidebar.
  wallpaper  full screen, below every window. Width/height = the screen,
             colour = the theme's "wallpaper" token.
Colours of every surface follow the homy-theme service (web/shell.js).

    homy-shell [surface …]      default: all surfaces
"""
from __future__ import annotations

import functools
import http.server
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

# Shared modules live in apps/common (copied next to this file by default.nix).
sys.path.append(str(Path(__file__).resolve().parent.parent / "common"))

import webengine

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
UI = Path(os.environ.get("HOMY_UI_DIR", "/run/current-system/sw/share/homy/ui"))
PORT = 47811                      # the pages and Qtile's setgroup hook talk to this

BAR_HEIGHT = 40                   # Qtile's top/bottom bars (BAR_HEIGHT in the Qtile config)

# name → window title (Qtile matches on it), size, behind everything?, transparent?
# size None = the screen above the bottom bar (the transparent top bar lies on
# top of it), "top" = the top bar (screen width × BAR_HEIGHT); Qtile pins the
# windows there.
SURFACES = {
    "wallpaper": {"title": "Homy Wallpaper", "size": None, "below": True, "transparent": False},
    "sidebar":   {"title": "Homy Sidebar", "size": (180, 520), "below": False, "transparent": True},
    "topbar":    {"title": "Homy Top Bar", "size": "top", "below": False, "transparent": True},
}

# Navigation surfaces: activeIndex (button position) → what a tap does.
#   group name  switch to that Qtile group (and highlight the button there)
#   "menu"      the app menu — Qtile's user hook "show_launcher" (it first moves
#               stray app windows out of the menu's group)
#   "power"     systemctl poweroff (sidebar button 4, like the old Shutdown button)
NAV = {
    "sidebar": {0: "1", 1: "2", 2: "3", 3: "4", 4: "power"},
    "topbar":  {0: "5", 1: "menu", 2: "8"},
}
MENU_GROUP = "9"                  # the menu's own group: highlights the menu button


def log(msg: str):
    print(f"[homy-shell] {msg}", flush=True)


def active_index(surface: str, group: str) -> int:
    """The button to highlight on a surface while `group` is shown (-1: none)."""
    for index, action in NAV[surface].items():
        if action == group or (action == "menu" and group == MENU_GROUP):
            return index
    return -1


def navigate(surface: str, index: int):
    """A button on a navigation surface was tapped (runs in a worker thread)."""
    action = NAV[surface].get(index)
    if action == "power":
        log("power button → systemctl poweroff")
        subprocess.run(["systemctl", "poweroff"])
    elif action == "menu":
        subprocess.run(["qtile", "cmd-obj", "-f", "fire_user_hook", "-a", "show_launcher"],
                       capture_output=True)
    elif action:
        subprocess.run(["qtile", "cmd-obj", "-o", "group", action, "-f", "toscreen"], capture_output=True)
    else:
        log(f"no action for {surface} button {index}")


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the pages (web/), the .riv files (/riv/) and the Rive runtime
    (/vendor/) from one origin, plus /group for Qtile."""
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".riv": "application/octet-stream"}
    on_group = staticmethod(lambda name: None)

    def translate_path(self, path):
        url_path = urllib.parse.urlparse(path).path
        if url_path.startswith("/riv/"):
            return str(UI / "riv" / Path(url_path).name)
        if url_path.startswith("/vendor/"):
            return str(UI / "runtime" / url_path[len("/vendor/"):])
        return super().translate_path(path)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/group":                     # from Qtile's setgroup hook
            name = urllib.parse.parse_qs(url.query).get("name", [""])[0]
            self.send_response(204)
            self.end_headers()
            self.on_group(name)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


def main():
    wanted = sys.argv[1:] or list(SURFACES)
    unknown = [s for s in wanted if s not in SURFACES]
    if unknown:
        sys.exit(f"homy-shell: unknown surface(s) {unknown}; known: {list(SURFACES)}")

    gpu = webengine.configure()

    from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow

    # One shell per session: the fixed port doubles as the lock.
    try:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", PORT), functools.partial(Handler, directory=str(WEB)))
    except OSError:
        log(f"port {PORT} in use — the shell is already running")
        sys.exit(0)

    class Bridge(QObject):
        group_changed = pyqtSignal(str)      # from the HTTP thread to the Qt thread

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Homy Shell")
    bridge = Bridge()
    # per navigation surface: its page, loaded yet?, the button to highlight
    nav = {s: {"index": active_index(s, "1"), "loaded": False, "page": None}   # Qtile starts on group 1
           for s in NAV if s in wanted}

    class Page(QWebEnginePage):
        def __init__(self, surface: str, parent):
            super().__init__(parent)
            self.surface = surface

        def javaScriptConsoleMessage(self, level, message, line, source):
            if not message.startswith("homy:"):
                if level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                    log(f"{self.surface}: js: {message} ({source}:{line})")
                return
            kind, _, data = message[5:].partition(" ")
            if self.surface in nav and kind == "navigate":
                threading.Thread(target=navigate, args=(self.surface, int(float(data))), daemon=True).start()
                return
            if self.surface in nav and kind == "loaded":
                nav[self.surface]["loaded"] = True
                self.runJavaScript(f"homy.setActive({nav[self.surface]['index']})")
            log(f"{self.surface}: {kind} {data}")

    def on_group(name: str):
        for surface, state in nav.items():
            state["index"] = active_index(surface, name)
            if state["loaded"]:
                state["page"].runJavaScript(f"homy.setActive({state['index']})")

    bridge.group_changed.connect(on_group)
    Handler.on_group = staticmethod(bridge.group_changed.emit)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    screen = app.primaryScreen().geometry()
    windows = []
    for name in wanted:
        spec = SURFACES[name]
        win = QMainWindow()
        win.setWindowTitle(spec["title"])
        flags = Qt.WindowType.FramelessWindowHint
        if spec["below"]:
            # _NET_WM_STATE_BELOW, and taps pass through: with bring_front_click a
            # tap on the wallpaper would otherwise raise it over everything.
            flags |= Qt.WindowType.WindowStaysOnBottomHint | Qt.WindowType.WindowTransparentForInput
        win.setWindowFlags(flags)
        view = QWebEngineView()
        page = Page(name, view)
        view.setPage(page)
        if spec["transparent"]:
            # Only what the Rive file draws is visible (needs the compositor —
            # picom — running, otherwise X11 shows black there).
            win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            view.setStyleSheet("background: transparent;")
            page.setBackgroundColor(Qt.GlobalColor.transparent)
        else:
            page.setBackgroundColor(Qt.GlobalColor.black)
        if name in nav:
            nav[name]["page"] = page
        view.setUrl(QUrl(f"http://127.0.0.1:{PORT}/{name}.html?renderer=webgl2"))
        win.setCentralWidget(view)
        if spec["size"] == "top":
            w, h = screen.width(), BAR_HEIGHT
        else:
            w, h = spec["size"] or (screen.width(), screen.height() - BAR_HEIGHT)
        win.setFixedSize(w, h)
        win.show()
        windows.append(win)

    log(f"surfaces: {', '.join(wanted)} — rendering: {'GPU' if gpu else 'software'} (webgl2)")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
