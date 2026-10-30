"""Homy sidebar — the right-hand navigation bar, drawn by Rive.

Plays the SideBar artboard of sidebar.riv (built from homy-design/Neo_Button,
see ui/sync.sh) with Rive's web runtime in a frameless QtWebEngine window.
Both come from the homy-ui package (HOMY_UI_DIR, set by the wrapper).
Qtile pins the window over its right bar ("Homy Sidebar" in
dotfiles/qtile/config.py).

  tap a button   → the file writes activeIndex → we switch the Qtile group
  group changes  → Qtile calls 127.0.0.1:47811/group?name=… → we set activeIndex
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
RIV = UI / "riv" / "sidebar.riv"
VENDOR = UI / "runtime"

TITLE = "Homy Sidebar"            # Qtile recognises the window by this
W, H = 180, 520                   # the SideBar artboard / Qtile's right bar
PORT = 47811                      # Qtile's setgroup hook talks to this

# activeIndex (button position) ↔ Qtile group. Button 4 (Switch) is the power
# button, like the old bar's Shutdown button.
INDEX_TO_GROUP = {0: "1", 1: "2", 2: "3", 3: "4"}
GROUP_TO_INDEX = {g: i for i, g in INDEX_TO_GROUP.items()}
POWER_INDEX = 4


def log(msg: str):
    print(f"[homy-sidebar] {msg}", flush=True)


def navigate(index: int):
    """A button was tapped (runs in a worker thread)."""
    if index == POWER_INDEX:
        log("power button → systemctl poweroff")
        subprocess.run(["systemctl", "poweroff"])
    elif index in INDEX_TO_GROUP:
        group = INDEX_TO_GROUP[index]
        subprocess.run(["qtile", "cmd-obj", "-o", "group", group, "-f", "toscreen"],
                       capture_output=True)
    else:
        log(f"no action for button {index}")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".riv": "application/octet-stream"}
    on_group = staticmethod(lambda name: None)

    def translate_path(self, path):
        url_path = urllib.parse.urlparse(path).path
        if url_path == "/sidebar.riv":
            return str(RIV)
        if url_path.startswith("/vendor/"):
            return str(VENDOR / url_path[len("/vendor/"):])
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
    gpu = webengine.configure()

    from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow

    # One sidebar per session: the fixed port doubles as the lock.
    try:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", PORT), functools.partial(Handler, directory=str(WEB)))
    except OSError:
        log(f"port {PORT} in use — a sidebar is already running")
        sys.exit(0)

    class Bridge(QObject):
        group_changed = pyqtSignal(str)      # from the HTTP thread to the Qt thread

    app = QApplication(sys.argv[:1])
    app.setApplicationName(TITLE)
    bridge = Bridge()
    state = {"index": 0, "loaded": False}    # Qtile starts on group 1 = Home

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if not message.startswith("homy:"):
                if level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                    log(f"js: {message} ({source}:{line})")
                return
            kind, _, data = message[5:].partition(" ")
            if kind == "navigate":
                threading.Thread(target=navigate, args=(int(float(data)),), daemon=True).start()
            elif kind == "loaded":
                state["loaded"] = True
                self.runJavaScript(f"homy.setActive({state['index']})")
                log(f"loaded {data}")
            else:
                log(f"{kind} {data}")

    def on_group(name: str):
        state["index"] = GROUP_TO_INDEX.get(name, -1)   # -1: no button for this group
        if state["loaded"]:
            page.runJavaScript(f"homy.setActive({state['index']})")

    bridge.group_changed.connect(on_group)
    Handler.on_group = staticmethod(bridge.group_changed.emit)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Fully transparent window: only what the Rive file draws is visible (needs
    # the compositor — picom — running, otherwise X11 shows black there).
    win = QMainWindow()
    win.setWindowTitle(TITLE)
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view = QWebEngineView()
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.setStyleSheet("background: transparent;")
    page = Page(view)
    view.setPage(page)
    page.setBackgroundColor(Qt.GlobalColor.transparent)
    renderer = "webgl2"      # the only Rive renderer that draws feathers / blend modes
    view.setUrl(QUrl(f"http://127.0.0.1:{PORT}/index.html?renderer={renderer}"))
    win.setCentralWidget(view)
    win.setFixedSize(W, H)
    win.show()
    log(f"rendering: {'GPU' if gpu else 'software'} ({renderer})")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
