"""Homy shell — the Rive-drawn parts of the desktop, in one process.

Every surface (sidebar, wallpaper, later the bars) is a frameless QtWebEngine
window playing one artboard of a .riv from the homy-ui package (HOMY_UI_DIR,
set by the wrapper). They share one Chromium (browser, GPU and renderer
processes), so a surface costs a page, not a whole browser. Qtile recognises
the windows by title and pins them (dotfiles/qtile/config.py, "Homy shell").

  sidebar    right edge, transparent. Tap → switch the Qtile group; Qtile
             reports group changes to 127.0.0.1:47811/group?name=… → highlight.
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

# name → window title (Qtile matches on it), size, behind everything?, transparent?
SURFACES = {
    "wallpaper": {"title": "Homy Wallpaper", "size": None, "below": True, "transparent": False},
    "sidebar":   {"title": "Homy Sidebar", "size": (180, 520), "below": False, "transparent": True},
}

# Sidebar: activeIndex (button position) ↔ Qtile group. Button 4 (Switch) is
# the power button, like the old bar's Shutdown button.
INDEX_TO_GROUP = {0: "1", 1: "2", 2: "3", 3: "4"}
GROUP_TO_INDEX = {g: i for i, g in INDEX_TO_GROUP.items()}
POWER_INDEX = 4


def log(msg: str):
    print(f"[homy-shell] {msg}", flush=True)


def navigate(index: int):
    """A sidebar button was tapped (runs in a worker thread)."""
    if index == POWER_INDEX:
        log("power button → systemctl poweroff")
        subprocess.run(["systemctl", "poweroff"])
    elif index in INDEX_TO_GROUP:
        subprocess.run(["qtile", "cmd-obj", "-o", "group", INDEX_TO_GROUP[index], "-f", "toscreen"],
                       capture_output=True)
    else:
        log(f"no action for sidebar button {index}")


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
    sidebar = {"index": 0, "loaded": False, "page": None}   # Qtile starts on group 1 = Home

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
            if self.surface == "sidebar" and kind == "navigate":
                threading.Thread(target=navigate, args=(int(float(data)),), daemon=True).start()
                return
            if self.surface == "sidebar" and kind == "loaded":
                sidebar["loaded"] = True
                self.runJavaScript(f"homy.setActive({sidebar['index']})")
            log(f"{self.surface}: {kind} {data}")

    def on_group(name: str):
        sidebar["index"] = GROUP_TO_INDEX.get(name, -1)   # -1: no button for this group
        if sidebar["loaded"]:
            sidebar["page"].runJavaScript(f"homy.setActive({sidebar['index']})")

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
        if name == "sidebar":
            sidebar["page"] = page
        view.setUrl(QUrl(f"http://127.0.0.1:{PORT}/{name}.html?renderer=webgl2"))
        win.setCentralWidget(view)
        w, h = spec["size"] or (screen.width(), screen.height())
        win.setFixedSize(w, h)
        win.show()
        windows.append(win)

    log(f"surfaces: {', '.join(wanted)} — rendering: {'GPU' if gpu else 'software'} (webgl2)")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
