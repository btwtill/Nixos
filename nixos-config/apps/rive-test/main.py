"""Rive prototype: plays a .riv file with Rive's web runtime, in the content area.

    rive-test [--chromium] [--renderer webgl2|canvas] [--fit contain|cover|layout|fill] [FILE.riv]

Two ways to host the page, to compare on the device:
  default     QtWebEngine (Chromium's engine) inside a frameless PyQt window,
              like the other apps
  --chromium  a separate Chromium window in app mode (no tabs / address bar)

Which .riv: FILE.riv if given, else the newest *.riv in ~/rive/, else the
bundled sample. Copy your own files to ~/rive/ to try them.

The page and the runtime are served from 127.0.0.1 because Chromium won't load
WASM or .riv files from file:// URLs.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
USER_RIV_DIR = Path.home() / "rive"
W, H = 814, 490

# Let Chromium use the Pi's GPU even if its blocklist says otherwise — the
# point of this test is to see real GPU performance. (QtWebEngine reads this.)
CHROMIUM_FLAGS = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization"]


def pick_riv(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    candidates = sorted(USER_RIV_DIR.glob("*.riv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else WEB / "sample.riv"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".riv": "application/octet-stream"}
    riv_path: Path = WEB / "sample.riv"

    def translate_path(self, path):
        if urllib.parse.urlparse(path).path == "/file.riv":
            return str(self.riv_path)
        return super().translate_path(path)

    def log_message(self, *args):
        pass                                     # quiet


def serve(riv: Path) -> str:
    """Start the local server in a thread; returns its base URL."""
    handler = functools.partial(Handler, directory=str(WEB))
    Handler.riv_path = riv
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def page_url(base: str, riv: Path, renderer: str, fit: str, engine: str) -> str:
    q = urllib.parse.urlencode({"renderer": renderer, "fit": fit, "engine": engine, "name": riv.name})
    return f"{base}/index.html?{q}"


def run_webengine(url: str):
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(CHROMIUM_FLAGS))
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication, QMainWindow

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            # Messages from the page (index.html `emit`) — the JS→Python half of
            # the bridge. Python→JS: self.runJavaScript('homy.set("X", 1)').
            if message.startswith("homy:"):
                print(f"[rive-test] {message[5:]}", flush=True)
            elif level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                print(f"[rive-test] js: {message} ({source}:{line})", flush=True)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Rive Test")
    win = QMainWindow()
    win.setWindowTitle("Rive Test")
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    view = QWebEngineView()
    view.setPage(Page(view))
    view.page().setBackgroundColor(Qt.GlobalColor.black)
    view.setUrl(QUrl(url))
    win.setCentralWidget(view)
    win.setFixedSize(W, H)
    win.show()
    sys.exit(app.exec())


def run_chromium(url: str):
    profile = Path.home() / ".cache" / "rive-test" / "chromium"
    prefs = profile / "Default" / "Preferences"
    if not prefs.exists():
        # Use the window manager's (i.e. no) frame instead of Chromium's own
        # title bar, so the app-mode window is frameless under Qtile.
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.write_text(json.dumps({"browser": {"custom_chrome_frame": False}}))
    cmd = ["chromium", f"--app={url}", f"--window-size={W},{H}",
           f"--user-data-dir={profile}",          # own instance (own window/PID)
           "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
           *CHROMIUM_FLAGS]
    sys.exit(subprocess.run(cmd).returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("riv", nargs="?")
    ap.add_argument("--chromium", action="store_true", help="host in a Chromium app window")
    ap.add_argument("--renderer", choices=["webgl2", "canvas"], default="webgl2")
    ap.add_argument("--fit", choices=["contain", "cover", "layout", "fill"], default="contain")
    args = ap.parse_args()

    riv = pick_riv(args.riv)
    if not riv.is_file():
        sys.exit(f"rive-test: {riv} not found")
    engine = "chromium" if args.chromium else "qtwebengine"
    url = page_url(serve(riv), riv, args.renderer, args.fit, engine)
    print(f"[rive-test] {riv} via {engine}: {url}", flush=True)
    run_chromium(url) if args.chromium else run_webengine(url)


if __name__ == "__main__":
    main()
