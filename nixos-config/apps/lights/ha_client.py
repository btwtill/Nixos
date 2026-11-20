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

    def get_light_full_state(self, entity_id: str) -> dict | None:
        """Returns {"intensity": 0-1, "hue": 0-360, "saturation": 0-1} or None on error.

        hue/saturation are None when HA doesn't report hs_color (e.g. white-only lights).
        """
        state = self.get_state(entity_id)
        if state is None:
            return None
        attrs = state.get("attributes", {})
        if state.get("state") == "off":
            intensity = 0.0
        else:
            brightness = attrs.get("brightness")
            intensity = max(0.0, min(1.0, brightness / 255.0)) if brightness is not None else 1.0
        hs = attrs.get("hs_color")
        if hs and len(hs) >= 2:
            hue        = float(hs[0]) % 360.0
            saturation = max(0.0, min(1.0, float(hs[1]) / 100.0))
        else:
            hue = saturation = None
        return {"intensity": intensity, "hue": hue, "saturation": saturation}

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


class LightSender:
    """Sends light changes to Home Assistant so the lights fade smoothly.

    What made changes jump before, and what this does instead:
      - no `transition` was sent, so each light used its integration's default
        (often: none). Every call here carries one.
      - brightness and colour went out as two separate calls whose fades cut
        each other off. Here they go out together, in one call.
      - a drag sent nothing until the finger paused (debounce), then one big
        step. Here a drag sends the latest value every `interval` seconds,
        with a fade as long as that interval, so the steps blend into one move.
      - every value went out on its own thread, so an older value could arrive
        after a newer one and the light jumped back. Here one thread sends
        everything in order, and only the latest value per light.

    Lights whose integration can't fade (no TRANSITION feature in Home
    Assistant, e.g. some Govee/Tuya bulbs) still step; that is the bulb.
    """

    DRAG_FADE = 0.4     # s: fade per step while dragging (a bit over `interval`, so they overlap)
    FINAL_FADE = 0.8    # s: fade for a finished change (drag released, scene applied)

    def __init__(self, ha: HAClient, interval: float = 0.3):
        import threading
        self._ha, self._interval = ha, interval
        self._wake = threading.Condition()
        self._pending: dict[str, dict] = {}     # entity → {"brightness": 0-1, "hs": (h, s), "final": bool}
        self._last: dict[str, float] = {}       # entity → when it was last sent
        threading.Thread(target=self._run, daemon=True).start()

    def update(self, entity_id: str, brightness: float | None = None,
               hs: tuple[float, float] | None = None, final: bool = False):
        """Queue a change; values not given stay as they are on the light."""
        with self._wake:
            p = self._pending.setdefault(entity_id, {"final": False})
            if brightness is not None:
                p["brightness"] = brightness
            if hs is not None:
                p["hs"] = hs
            p["final"] = p["final"] or final
            self._wake.notify()

    def _run(self):
        import time
        while True:
            with self._wake:
                while True:
                    now = time.monotonic()
                    # a light is due once its interval since the last send has passed;
                    # a final value doesn't wait (the drag is over)
                    due = [e for e, p in self._pending.items()
                           if p["final"] or now - self._last.get(e, 0) >= self._interval]
                    if due:
                        break
                    if self._pending:
                        wait = min(self._interval - (now - self._last.get(e, 0)) for e in self._pending)
                        self._wake.wait(max(wait, 0.01))
                    else:
                        self._wake.wait()
                batch = {e: self._pending.pop(e) for e in due}
            for entity_id, p in batch.items():
                self._last[entity_id] = time.monotonic()
                self._send(entity_id, p)

    def _send(self, entity_id: str, p: dict):
        fade = self.FINAL_FADE if p["final"] else self.DRAG_FADE
        brightness = p.get("brightness")
        if brightness is not None and round(brightness * 100) <= 0:
            self._ha.call_service("light", "turn_off", {"entity_id": entity_id, "transition": fade})
            return
        data: dict = {"entity_id": entity_id, "transition": fade}
        if brightness is not None:
            data["brightness_pct"] = round(brightness * 100)
        if "hs" in p:
            hue, sat = p["hs"]
            data["hs_color"] = [round(hue % 360, 1), round(sat * 100, 1)]
        self._ha.call_service("light", "turn_on", data)
