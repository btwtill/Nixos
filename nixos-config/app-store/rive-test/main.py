"""Rive prototype: plays a .riv file with Rive's web runtime, in the content area.

Install from the app store folder:   homy-apps install ~/Nixos/nixos-config/app-store/rive-test

    homy-python main.py [--chromium] [--renderer webgl2|canvas] [--fit contain|cover|layout|fill] [FILE.riv]

Two ways to host the page, switchable from the overlay ("engine"):
  default     QtWebEngine (Chromium's engine) inside a frameless PyQt window
  --chromium  a separate Chromium window in app mode (no tabs / address bar)

Which .riv: FILE.riv if given, else the newest *.riv in ~/rive/, else Rive's
public sample. Copy your own files to ~/rive/ to try them.

Rive's web runtime (pinned version, checked against known SHA-256 hashes) is
downloaded on first start into ~/.cache/homy/rive-runtime/ and used offline
from then on — so this folder stays small and other Rive apps can share it.

Everything is served from 127.0.0.1 because Chromium won't load WASM or .riv
files from file:// URLs.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tarfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
USER_RIV_DIR = Path.home() / "rive"
W, H = 814, 490

RIVE_VERSION = "2.47.0"
RUNTIME_DIR = Path.home() / ".cache" / "homy" / "rive-runtime"
RUNTIMES = {   # renderer -> SHA-256 (base64) of the npm tarball
    "canvas": "5qViveyfEDatZBihihKF/XDr3FT8ByDAbEZllTzXqhE=",
    "webgl2": "Wy73SaYIcsFXkWfeOpCXYiXaeFvVXaDxQ4hZD4VULMw=",
}
RUNTIME_FILES = ("rive.js", "rive.wasm", "rive_fallback.wasm")
SAMPLE_URL = "https://cdn.rive.app/animations/vehicles.riv"
SAMPLE_SHA256 = "RrslDN4LAiOhX63awz0I+gDUtqzrwuToJzka4BE3aKM="

# Let Chromium use the Pi's GPU even if its blocklist says otherwise — the
# point of this test is to see real GPU performance. (QtWebEngine reads this.)
CHROMIUM_FLAGS = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization"]


def log(msg: str):
    print(f"[rive-test] {msg}", flush=True)


# ── Runtime download (first start only) ───────────────────────────────────────

def _download(url: str, sha256_b64: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    if base64.b64encode(hashlib.sha256(data).digest()).decode() != sha256_b64:
        raise ValueError(f"checksum mismatch for {url}")
    return data


def ensure_runtime() -> Path:
    """Rive runtimes + sample in the shared cache; downloads what's missing."""
    root = RUNTIME_DIR / RIVE_VERSION
    for renderer, sha in RUNTIMES.items():
        dest = root / renderer
        if all((dest / f).is_file() for f in RUNTIME_FILES):
            continue
        url = f"https://registry.npmjs.org/@rive-app/{renderer}/-/{renderer}-{RIVE_VERSION}.tgz"
        log(f"downloading Rive {renderer} runtime {RIVE_VERSION} …")
        try:
            data = _download(url, sha)
        except Exception as e:
            log(f"could not download the {renderer} runtime: {e}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for name in RUNTIME_FILES:
                (dest / name).write_bytes(tar.extractfile(f"package/{name}").read())
    sample = RUNTIME_DIR / "sample.riv"
    if not sample.is_file():
        try:
            sample.write_bytes(_download(SAMPLE_URL, SAMPLE_SHA256))
        except Exception as e:
            log(f"could not download the sample .riv: {e}")
    return root


def pick_riv(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    candidates = sorted(USER_RIV_DIR.glob("*.riv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else RUNTIME_DIR / "sample.riv"


# ── Local web server ──────────────────────────────────────────────────────────

class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".riv": "application/octet-stream"}
    riv_path: Path
    runtime_root: Path
    on_switch_engine = staticmethod(lambda renderer: None)

    def translate_path(self, path):
        url_path = urllib.parse.urlparse(path).path
        if url_path == "/file.riv":
            return str(self.riv_path)
        if url_path.startswith("/vendor/"):
            return str(self.runtime_root / url_path[len("/vendor/"):])
        return super().translate_path(path)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/switch-engine":
            renderer = urllib.parse.parse_qs(url.query).get("renderer", ["webgl2"])[0]
            self.send_response(204)
            self.end_headers()
            self.on_switch_engine(renderer)
            return
        super().do_GET()

    def log_message(self, *args):
        pass                                     # quiet


def serve(riv: Path, runtime_root: Path, on_switch_engine) -> str:
    """Start the local server in a thread; returns its base URL."""
    Handler.riv_path, Handler.runtime_root = riv, runtime_root
    Handler.on_switch_engine = staticmethod(on_switch_engine)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(WEB)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def page_url(base: str, riv: Path, renderer: str, fit: str, engine: str) -> str:
    q = urllib.parse.urlencode({"renderer": renderer, "fit": fit, "engine": engine, "name": riv.name})
    return f"{base}/index.html?{q}"


# ── Hosts ─────────────────────────────────────────────────────────────────────

_chromium: subprocess.Popen | None = None


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
                log(message[5:])
            elif level != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                log(f"js: {message} ({source}:{line})")

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
    global _chromium
    profile = Path.home() / ".cache" / "rive-test" / "chromium"
    prefs = profile / "Default" / "Preferences"
    if not prefs.exists():
        # Use the window manager's (i.e. no) frame instead of Chromium's own
        # title bar, so the app-mode window is frameless under Qtile.
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.write_text(json.dumps({"browser": {"custom_chrome_frame": False}}))
    try:
        _chromium = subprocess.Popen(
            ["chromium", f"--app={url}", f"--window-size={W},{H}",
             f"--user-data-dir={profile}",          # own instance (own window/PID)
             "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
             *CHROMIUM_FLAGS])
    except FileNotFoundError:
        log("chromium is not installed on this host — using QtWebEngine instead")
        run_webengine(url.replace("engine=chromium", "engine=qtwebengine"))
        return
    sys.exit(_chromium.wait())


def restart_with(args: argparse.Namespace, chromium: bool, renderer: str):
    """Restart this app in the other engine (same process id and environment,
    so it stays in its Qtile group)."""
    argv = [sys.executable, str(Path(__file__).resolve()),
            "--renderer", renderer, "--fit", args.fit]
    if chromium:
        argv.append("--chromium")
    if args.riv:
        argv.append(args.riv)

    def go():
        if _chromium and _chromium.poll() is None:
            _chromium.terminate()
            _chromium.wait(timeout=5)
        os.execv(sys.executable, argv)

    threading.Timer(0.2, go).start()             # let the HTTP reply go out first


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("riv", nargs="?")
    ap.add_argument("--chromium", action="store_true", help="host in a Chromium app window")
    ap.add_argument("--renderer", choices=["webgl2", "canvas"], default="webgl2")
    ap.add_argument("--fit", choices=["contain", "cover", "layout", "fill"], default="contain")
    args = ap.parse_args()

    runtime_root = ensure_runtime()
    riv = pick_riv(args.riv)
    engine = "chromium" if args.chromium else "qtwebengine"
    base = serve(riv, runtime_root,
                 lambda renderer: restart_with(args, not args.chromium, renderer))
    url = page_url(base, riv, args.renderer, args.fit, engine)
    log(f"{riv} via {engine}: {url}")
    run_chromium(url) if args.chromium else run_webengine(url)


if __name__ == "__main__":
    main()
