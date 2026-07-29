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

    # ── weather ──────────────────────────────────────────────────────────────

    def get_weather_state(self, entity_id: str) -> dict | None:
        return self.get_state(entity_id)

    def get_weather_forecast(self, entity_id: str) -> list | None:
        """Hourly forecast list, or None if unavailable.

        Tries the state attributes first (older HA), then the HA 2024.3+
        ?return_response service endpoint, returning the raw body to the
        caller for debug logging.
        """
        state = self.get_state(entity_id)
        if state is not None:
            fc = state.get("attributes", {}).get("forecast")
            if fc:
                return fc
        # HA 2024.3+: ?return_response returns the service response directly.
        # Response body: {"service_response": {entity_id: {"forecast": [...]}},
        #                 "changed_states": [...]}
        req = urllib.request.Request(
            f"{self._base}/api/services/weather/get_forecasts?return_response",
            data=json.dumps({"entity_id": entity_id, "type": "hourly"}).encode(),
            headers=self._headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read())
                # unwrap service_response envelope if present
                inner = body.get("service_response", body) if isinstance(body, dict) else body
                if isinstance(inner, dict) and entity_id in inner:
                    fc = inner[entity_id].get("forecast")
                    if fc:
                        return fc
                self._last_forecast_raw = repr(body)[:300]
        except Exception as exc:
            self._last_forecast_raw = repr(exc)[:300]
        return None

    _last_forecast_raw: str = "(not called yet)"

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
