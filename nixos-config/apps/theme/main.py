"""homy-theme — the colour theme service.

Holds the themes (each one a full set of colour tokens), remembers which one
is active, and tells every running UI when it changes. Rive apps apply the
tokens to their global `Theme` view model by name.

Themes
  built-in   themes.json next to this file (read-only)
  user       ~/.config/homy/themes/<id>.json  (created through the API, e.g. by
             the theme-lab app); a user theme can't reuse a built-in id
Active     ~/.config/homy/theme-active  (survives reboots)

HTTP API on 127.0.0.1:47820 (CORS open, local only)
  GET    /tokens            token names → descriptions
  GET    /themes            {"active": id, "themes": [{id, name, builtin}]}
  GET    /themes/<id>       {id, name, builtin, tokens}
  PUT    /themes/<id>       {name?, tokens} — create/update a user theme; tokens
                            are merged onto the default theme, so all exist
  DELETE /themes/<id>       remove a user theme (falls back to the default if active)
  GET    /active            the active theme, like /themes/<id>
  POST   /active            {"id": …} — switch theme
  GET    /events            Server-Sent Events: the active theme now and on
                            every change (EventSource in a web page)
Tokens are "#RRGGBB" strings.
"""
from __future__ import annotations

import http.server
import json
import queue
import re
import sys
import threading
from pathlib import Path

PORT = 47820
HERE = Path(__file__).resolve().parent
CONFIG = Path.home() / ".config" / "homy"
USER_DIR = CONFIG / "themes"
ACTIVE_FILE = CONFIG / "theme-active"
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def log(msg: str):
    print(f"[homy-theme] {msg}", flush=True)


class Store:
    def __init__(self):
        data = json.loads((HERE / "themes.json").read_text())
        self.tokens: dict[str, str] = data["tokens"]
        self.builtin = {t["id"]: {**t, "builtin": True} for t in data["themes"]}
        self.default = data["default"]
        self.lock = threading.Lock()
        self.listeners: list[queue.Queue] = []
        try:
            active = ACTIVE_FILE.read_text().strip()
        except OSError:
            active = ""
        self.active = active if self.get(active) else self.default

    # ── themes ────────────────────────────────────────────────────────────────
    def user_themes(self) -> dict[str, dict]:
        out = {}
        for f in sorted(USER_DIR.glob("*.json")) if USER_DIR.is_dir() else []:
            try:
                t = json.loads(f.read_text())
                out[t["id"]] = {**t, "builtin": False}
            except (OSError, ValueError, KeyError):
                log(f"ignoring unreadable theme {f}")
        return out

    def all(self) -> dict[str, dict]:
        return {**self.user_themes(), **self.builtin}       # built-ins win on id clashes

    def get(self, theme_id: str) -> dict | None:
        return self.all().get(theme_id)

    def put(self, theme_id: str, body: dict) -> dict:
        if theme_id in self.builtin:
            raise PermissionError(f"'{theme_id}' is a built-in theme")
        if not ID.match(theme_id):
            raise ValueError("id must be lowercase letters, digits and dashes")
        tokens = dict(self.builtin[self.default]["tokens"])
        for name, value in (body.get("tokens") or {}).items():
            if name not in self.tokens:
                raise ValueError(f"unknown token '{name}'")
            if not COLOR.match(str(value)):
                raise ValueError(f"{name}: expected #RRGGBB, got {value!r}")
            tokens[name] = value.upper()
        theme = {"id": theme_id, "name": str(body.get("name") or theme_id), "tokens": tokens}
        USER_DIR.mkdir(parents=True, exist_ok=True)
        (USER_DIR / f"{theme_id}.json").write_text(json.dumps(theme, indent=2))
        if theme_id == self.active:
            self.broadcast()
        return {**theme, "builtin": False}

    def delete(self, theme_id: str):
        if theme_id in self.builtin:
            raise PermissionError(f"'{theme_id}' is a built-in theme")
        (USER_DIR / f"{theme_id}.json").unlink(missing_ok=True)
        if theme_id == self.active:
            self.set_active(self.default)

    def set_active(self, theme_id: str):
        if not self.get(theme_id):
            raise KeyError(theme_id)
        self.active = theme_id
        CONFIG.mkdir(parents=True, exist_ok=True)
        ACTIVE_FILE.write_text(theme_id)
        log(f"active theme: {theme_id}")
        self.broadcast()

    # ── live updates ──────────────────────────────────────────────────────────
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.listeners.append(q)
        q.put(self.get(self.active))
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def broadcast(self):
        theme = self.get(self.active)
        with self.lock:
            for q in self.listeners:
                q.put(theme)


STORE: Store


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status: int, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _route(self) -> list[str]:
        return [p for p in self.path.split("?")[0].split("/") if p]

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        r = self._route()
        if r == ["tokens"]:
            return self._json(200, STORE.tokens)
        if r == ["themes"]:
            return self._json(200, {"active": STORE.active, "themes": [
                {"id": t["id"], "name": t["name"], "builtin": t["builtin"]} for t in STORE.all().values()]})
        if len(r) == 2 and r[0] == "themes":
            t = STORE.get(r[1])
            return self._json(200, t) if t else self._json(404, {"error": "no such theme"})
        if r == ["active"]:
            return self._json(200, STORE.get(STORE.active))
        if r == ["events"]:
            return self._events()
        self._json(404, {"error": "not found"})

    def do_PUT(self):
        r = self._route()
        if len(r) != 2 or r[0] != "themes":
            return self._json(404, {"error": "not found"})
        try:
            self._json(200, STORE.put(r[1], self._body()))
        except PermissionError as e:
            self._json(403, {"error": str(e)})
        except ValueError as e:
            self._json(400, {"error": str(e)})

    def do_DELETE(self):
        r = self._route()
        if len(r) != 2 or r[0] != "themes":
            return self._json(404, {"error": "not found"})
        try:
            STORE.delete(r[1])
            self._json(200, {"deleted": r[1]})
        except PermissionError as e:
            self._json(403, {"error": str(e)})

    def do_POST(self):
        if self._route() != ["active"]:
            return self._json(404, {"error": "not found"})
        try:
            STORE.set_active(str(self._body().get("id")))
            self._json(200, STORE.get(STORE.active))
        except KeyError:
            self._json(404, {"error": "no such theme"})

    def _events(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = STORE.subscribe()
        try:
            while True:
                try:
                    theme = q.get(timeout=20)
                    self.wfile.write(f"data: {json.dumps(theme)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            STORE.unsubscribe(q)


def main():
    global STORE
    STORE = Store()
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        log(f"port {PORT} in use — already running?")
        sys.exit(1)
    server.daemon_threads = True
    log(f"serving on 127.0.0.1:{PORT}, active theme: {STORE.active}")
    server.serve_forever()


if __name__ == "__main__":
    main()
