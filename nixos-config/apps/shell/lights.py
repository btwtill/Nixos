"""The Lights app (homy-neo-hmi's LightsApp): lights placed on the floorplan.

So far one function: the add-light button (the bulb with the plus) puts a new
light on the plan, at the free spot closest to the middle. The lights are kept
in ~/.config/homy/lights.json:
  {"markers": [{"x": 375, "y": 176}, …]}
x/y: the light's centre on the floorplan (750 × 353).

  homy-hmi → here   number lights/add 1|0|2                  the button: down, up, slid off
  here → homy-hmi   list lights/floorplan/markers add PlacedLightInterface   one more light
                    number lights/floorplan/markers/3/x 245  its marker's top left

The lights are a list in the file (FloorPlan's `markers`, one PlacedLight per
item), so there is no fixed number of them.
"""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path

STORE = Path.home() / ".config" / "homy" / "lights.json"

LIST = "lights/floorplan/markers"
ITEM = "PlacedLightInterface"   # the view model of one list item (artboard PlacedLight)
SIZE = 100              # the LightMarker artboard
PLAN_W, PLAN_H = 750, 353
SPACING = 110           # new lights are placed at least this far apart


class Lights:
    def __init__(self, send, log):
        self.send, self.log = send, log
        self.lock = threading.Lock()
        self.markers: list[dict] = self._load()
        self.pressed = False

    def ready(self):
        """homy-hmi (re)started: watch the button, show the lights."""
        self.send("watch lights/add")
        with self.lock:
            self.send(f"list {LIST} clear")
            for m in range(len(self.markers)):
                self.send(f"list {LIST} add {ITEM}")
                self._show(m)

    def on_number(self, path: str, value: float) -> bool:
        if path != "lights/add":
            return False
        with self.lock:
            if value == 1:
                self.pressed = True
            elif value == 0 and self.pressed:    # a tap: down and up on the button
                self.pressed = False
                self._add()
            else:
                self.pressed = False             # slid off: no tap
        return True

    def _add(self):
        x, y = self._free_spot()
        self.markers.append({"x": x, "y": y})
        self._save()
        self.send(f"list {LIST} add {ITEM}")
        self._show(len(self.markers) - 1)
        self.log(f"lights: light {len(self.markers) - 1} added at {x:.0f},{y:.0f}")

    def _free_spot(self) -> tuple[float, float]:
        """the spot closest to the middle of the plan that no light covers"""
        cx, cy = PLAN_W / 2, PLAN_H / 2
        spots = [(cx + dx * SPACING, cy + dy * SPACING) for dx in range(-3, 4) for dy in range(-1, 2)]
        spots = [(x, y) for x, y in spots if SIZE / 2 <= x <= PLAN_W - SIZE / 2 and SIZE / 2 <= y <= PLAN_H - SIZE / 2]
        spots.sort(key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
        for x, y in spots:
            if all(math.hypot(x - m["x"], y - m["y"]) >= SPACING - 1 for m in self.markers):
                return x, y
        return cx, cy                             # all taken: on top of the others

    def _show(self, m: int):
        self.send(f"number {LIST}/{m}/x {self.markers[m]['x'] - SIZE / 2}")
        self.send(f"number {LIST}/{m}/y {self.markers[m]['y'] - SIZE / 2}")

    def _load(self) -> list[dict]:
        try:
            markers = json.loads(STORE.read_text()).get("markers", [])
        except (OSError, json.JSONDecodeError, AttributeError):
            return []
        return [{**m, "x": float(m.get("x", PLAN_W / 2)), "y": float(m.get("y", PLAN_H / 2))}
                for m in markers if isinstance(m, dict)]

    def _save(self):
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"markers": self.markers}, indent=2))
            tmp.replace(STORE)
        except OSError as e:
            self.log(f"lights: cannot save {STORE} ({e})")
