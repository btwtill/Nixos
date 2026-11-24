"""The Lights app (homy-neo-hmi's LightsApp): lights placed on the floorplan.

  add-light button (bulb with plus)  a new light, at the free spot closest to
                                     the middle of the plan
  settings button (gear)             edit mode on/off: the lights show the move
                                     icon and can be dragged; the pages don't
                                     scroll meanwhile

The lights are kept in ~/.config/homy/lights.json:
  {"markers": [{"x": 375, "y": 176}, …]}
x/y: the light's centre on the floorplan (750 × 353).

  homy-hmi → here   number lights/add 1|0|2                  the button: down, up, slid off
                    number lights/editPress 1|0|2            the gear
                    number lights/floorplan/markers/3/x 280  a light was dragged (edit mode)
  here → homy-hmi   list lights/floorplan/markers add PlacedLightInterface   one more light
                    number lights/floorplan/markers/3/x 245  its marker's top left
                    number lights/edit 1                     the gear highlighted
                    number lights/scroll 0                   the pages don't scroll
                    number lights/floorplan/markers/3/edit 1 the light can be dragged
                    number lights/floorplan/markers/3/marker/icon 1   the move icon

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
SAVE_AFTER = 1.0        # s: a dragged light is saved once it rests this long


class Lights:
    def __init__(self, send, log):
        self.send, self.log = send, log
        self.lock = threading.Lock()
        self.markers: list[dict] = self._load()
        self.pressed: set[str] = set()           # buttons with a finger down on them
        self.edit = False
        self.save_timer: threading.Timer | None = None

    def ready(self):
        """homy-hmi (re)started: watch the buttons, show the lights."""
        self.send("watch lights/add")
        self.send("watch lights/editPress")
        with self.lock:
            self._show_edit()
            self.send(f"list {LIST} clear")
            for m in range(len(self.markers)):
                self._add_item(m)

    def on_number(self, path: str, value: float) -> bool:
        if not path.startswith("lights/"):
            return False
        with self.lock:
            if path == "lights/add":
                if self._tapped(path, value):
                    self._add()
            elif path == "lights/editPress":
                if self._tapped(path, value):
                    self.edit = not self.edit
                    self._show_edit()
                    for m in range(len(self.markers)):
                        self._show_edit_item(m)
                    if not self.edit:
                        self._save()
            elif path.startswith(LIST + "/") and path.endswith(("/x", "/y")):
                self._dragged(int(path.split("/")[3]), path[-1], value)
            else:
                return False
        return True

    def _tapped(self, path: str, value: float) -> bool:
        """a tap: the finger went down and came up on the button (2: slid off)"""
        if value == 1:
            self.pressed.add(path)
            return False
        was_down = path in self.pressed
        self.pressed.discard(path)
        return was_down and value == 0

    def _add(self):
        x, y = self._free_spot()
        self.markers.append({"x": x, "y": y})
        self._save()
        self._add_item(len(self.markers) - 1)
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

    def _dragged(self, m: int, axis: str, value: float):
        """a light was dragged in edit mode: keep it on the plan, save it once it rests"""
        if m >= len(self.markers):
            return
        limit = (PLAN_W if axis == "x" else PLAN_H) - SIZE
        top_left = max(0.0, min(limit, value))
        if top_left != value:                     # dragged off the plan: back to the edge
            self.send(f"number {LIST}/{m}/{axis} {top_left}")
        self.markers[m][axis] = top_left + SIZE / 2
        if self.save_timer:
            self.save_timer.cancel()
        self.save_timer = threading.Timer(SAVE_AFTER, self._save_locked)
        self.save_timer.daemon = True
        self.save_timer.start()

    def _save_locked(self):
        with self.lock:
            self._save()

    def _add_item(self, m: int):
        """one more item in the file's list, for light m"""
        self.send(f"list {LIST} add {ITEM}")
        for axis in ("x", "y"):
            self.send(f"watch {LIST}/{m}/{axis}")
        self._show(m)
        self._show_edit_item(m)

    def _show(self, m: int):
        self.send(f"number {LIST}/{m}/x {self.markers[m]['x'] - SIZE / 2}")
        self.send(f"number {LIST}/{m}/y {self.markers[m]['y'] - SIZE / 2}")

    def _show_edit(self):
        self.send(f"number lights/edit {1 if self.edit else 0}")
        self.send(f"number lights/scroll {0 if self.edit else 1}")

    def _show_edit_item(self, m: int):
        self.send(f"number {LIST}/{m}/edit {1 if self.edit else 0}")
        self.send(f"number {LIST}/{m}/marker/icon {1 if self.edit else 0}")

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
