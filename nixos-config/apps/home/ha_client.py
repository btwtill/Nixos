"""Minimal Home Assistant REST API client (stdlib only, no extra dependency).

All calls are blocking — callers running on the Qt main thread should
dispatch them via a background thread and marshal results back through a
Qt signal (see main.py).
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request


class HAClient:
    def __init__(self, base_url: str, token: str, timeout: float = 3.0):
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def get_state(self, entity_id: str) -> dict | None:
        req = urllib.request.Request(
            f"{self._base}/api/states/{entity_id}",
            headers=self._headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    def call_service(self, domain: str, service: str, data: dict) -> bool:
        req = urllib.request.Request(
            f"{self._base}/api/services/{domain}/{service}",
            data=json.dumps(data).encode(),
            headers=self._headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    # ── lights ───────────────────────────────────────────────────────────────

    def get_light_brightness_pct(self, entity_id: str) -> float | None:
        """Current brightness as 0.0-1.0, or None if the state couldn't be read."""
        state = self.get_state(entity_id)
        if state is None:
            return None
        if state.get("state") != "on":
            return 0.0
        brightness = state.get("attributes", {}).get("brightness")
        if brightness is None:
            return 1.0  # on, but doesn't report brightness (non-dimmable)
        return max(0.0, min(1.0, brightness / 255.0))

    def set_light_brightness(self, entity_id: str, pct: int) -> bool:
        pct = max(0, min(100, int(pct)))
        if pct == 0:
            return self.call_service("light", "turn_off", {"entity_id": entity_id})
        return self.call_service(
            "light", "turn_on",
            {"entity_id": entity_id, "brightness_pct": pct},
        )
