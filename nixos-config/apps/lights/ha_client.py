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

    def get_all_lights(self) -> tuple[list[dict], str]:
        """Fetch all light.* entities, sorted by friendly name.

        Returns (lights, error_msg). error_msg is empty on success.
        """
        req = urllib.request.Request(
            f"{self._base}/api/states",
            headers=self._headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                states = json.loads(raw)
        except urllib.error.HTTPError as exc:
            return [], f"HTTP {exc.code} {exc.reason}"
        except urllib.error.URLError as exc:
            return [], f"URLError: {exc.reason}"
        except OSError as exc:
            return [], f"OSError: {exc}"
        except json.JSONDecodeError as exc:
            return [], f"JSONDecodeError: {exc}"
        if not isinstance(states, list):
            return [], f"unexpected response type: {type(states).__name__}"
        result = []
        for s in states:
            eid = s.get("entity_id", "")
            if eid.startswith("light."):
                fname = s.get("attributes", {}).get("friendly_name", eid)
                result.append({"entity_id": eid, "friendly_name": fname})
        result.sort(key=lambda x: x["friendly_name"].lower())
        return result, ""

    def get_light_brightness_pct(self, entity_id: str) -> float | None:
        state = self.get_state(entity_id)
        if state is None:
            return None
        if state.get("state") != "on":
            return 0.0
        brightness = state.get("attributes", {}).get("brightness")
        if brightness is None:
            return 1.0
        return max(0.0, min(1.0, brightness / 255.0))

    def set_light_brightness(self, entity_id: str, pct: int) -> bool:
        pct = max(0, min(100, int(pct)))
        if pct == 0:
            return self.call_service("light", "turn_off", {"entity_id": entity_id})
        return self.call_service(
            "light", "turn_on",
            {"entity_id": entity_id, "brightness_pct": pct},
        )

    def set_light_color(self, entity_id: str, hue: float, saturation: float) -> bool:
        """hue: 0–360, saturation: 0–1."""
        return self.call_service(
            "light", "turn_on",
            {"entity_id": entity_id, "hs_color": [round(hue, 1), round(saturation * 100, 1)]},
        )
