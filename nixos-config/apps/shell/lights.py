"""The Lights app (homy-neo-hmi's LightsApp): lights placed on the floorplan.

  add-light button (bulb with plus)  a new light, at the free spot closest to
                                     the middle of the plan
  settings button (gear)             edit mode on/off: the lights show the move
                                     icon and can be dragged; the pages don't
                                     scroll meanwhile
  a light, tapped                    on/off, when the finger lifts
  a light, held (HOLD seconds)       selected: an orange ring; the release
                                     after it does not switch the light
  the plan, tapped beside the lights the selection is cleared

A light shows what its Home Assistant light is doing: `level` (brightness
0-1, 0 = off) and `color`; the file fades both over 1.5 s. Until a light is
connected to one (`entities`, a later step), it shows the not-connected icon
and a tap switches only its look (level 1 / 0, kept in the file below).
Connected, both directions: a tap/drag here goes to Home Assistant, and
changes from elsewhere (the phone app, a switch) arrive through
`show_ha_state`, which maps HA's state to level and colour.

The lights are kept in ~/.config/homy/lights.json:
  {"markers": [{"x": 375, "y": 176}, …]}
x/y: the light's centre on the floorplan (750 × 353).

  homy-hmi → here   number lights/add 1|0|2                  the button: down, up, slid off
                    number lights/editPress 1|0|2            the gear
                    number lights/floorplan/markers/3/x 280  a light was dragged (edit mode)
                    number lights/floorplan/markers/3/press  a light: 1 down, 0 up, 2 slid off
                    number lights/floorplan/planPress        the plan (also under a light)
  here → homy-hmi   list lights/floorplan/markers add PlacedLightInterface   one more light
                    number lights/floorplan/markers/3/x 245  its marker's top left
                    number lights/edit 1                     the gear highlighted
                    number lights/scroll 0                   the pages don't scroll
                    number lights/floorplan/markers/3/edit 1 the light can be dragged
                    number lights/floorplan/markers/3/marker/icon 1   0 bulb, 1 move, 2 not connected
                    number lights/floorplan/markers/3/marker/level 0.5  brightness (0: off)
                    color lights/floorplan/markers/3/marker/color #FFD9A0   the ring's colour
                    number lights/floorplan/markers/3/marker/selected 1   the orange ring

The lights are a list in the file (FloorPlan's `markers`, one PlacedLight per
item), so there is no fixed number of them.
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

STORE = Path.home() / ".config" / "homy" / "lights.json"

LIST = "lights/floorplan/markers"
ITEM = "PlacedLightInterface"   # the view model of one list item (artboard PlacedLight)
SIZE = 100              # the LightMarker artboard
PLAN_W, PLAN_H = 750, 353
SPACING = 110           # new lights are placed at least this far apart
SAVE_AFTER = 1.0        # s: a dragged light is saved once it rests this long
HOLD = 0.5              # s: a light held this long is selected instead of switched
SAME_TOUCH = 0.1        # s: a plan press this close to a light press is that light's touch
DEFAULT_COLOR = "#EADFB6"   # the ring of a light with no colour (white light, not connected)
ICON_BULB, ICON_MOVE, ICON_NOT_CONNECTED = 0, 1, 2


class Lights:
    def __init__(self, send, log):
        self.send, self.log = send, log
        self.lock = threading.Lock()
        self.markers: list[dict] = self._load()
        self.pressed: set[str] = set()           # buttons with a finger down on them
        self.edit = False
        self.save_timer: threading.Timer | None = None
        self.selected: int | None = None
        self.hold_timer: threading.Timer | None = None
        self.held = False                        # the current touch selected its light
        self.light_down = -1.0                   # when a light was last pressed
        self.plan_down = -1.0                    # when the plan was last pressed

    def ready(self):
        """homy-hmi (re)started: watch the buttons, show the lights."""
        self.send("watch lights/add")
        self.send("watch lights/editPress")
        self.send("watch lights/floorplan/planPress")
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
                    if self.edit:
                        self._select(None)               # editing moves lights, nothing is selected
                    self._show_edit()
                    for m in range(len(self.markers)):
                        self._show_edit_item(m)
                    if not self.edit:
                        self._save()
            elif path.startswith(LIST + "/") and path.endswith(("/x", "/y")):
                self._dragged(int(path.split("/")[3]), path[-1], value)
            elif path.startswith(LIST + "/") and path.endswith("/press"):
                self._light_press(int(path.split("/")[3]), value)
            elif path == "lights/floorplan/planPress":
                self._plan_press(value)
            else:
                return False
        return True

    def _light_press(self, m: int, value: float):
        """tap: on/off when the finger lifts; hold: select (that release does nothing)"""
        if m >= len(self.markers) or self.edit:
            return
        if self.hold_timer:
            self.hold_timer.cancel()
            self.hold_timer = None
        if value == 1:
            self.light_down = time.monotonic()
            self.held = False
            self.hold_timer = threading.Timer(HOLD, self._hold, (m,))
            self.hold_timer.daemon = True
            self.hold_timer.start()
        elif value == 0 and not self.held:
            mk = self.markers[m]                     # not connected yet: only its look
            mk["level"] = 0.0 if mk.get("level", 0) > 0 else 1.0
            self._show_state(m)
            self._save()
        # 2: slid off, nothing

    def _hold(self, m: int):
        with self.lock:
            self.hold_timer = None
            self.held = True
            self._select(m)

    def _plan_press(self, value: float):
        """the plan tapped beside the lights: clear the selection. A press on a
        light reaches the plan too (it lies underneath): those are left out."""
        now = time.monotonic()
        if value == 1:
            self.plan_down = now
        elif value == 0 and not self.edit and self.light_down < self.plan_down - SAME_TOUCH:
            self._select(None)

    def _select(self, m: int | None):
        if self.selected == m:
            return
        if self.selected is not None and self.selected < len(self.markers):
            self.send(f"number {LIST}/{self.selected}/marker/selected 0")
        self.selected = m
        if m is not None:
            self.send(f"number {LIST}/{m}/marker/selected 1")

    def _show_state(self, m: int):
        mk = self.markers[m]
        self.send(f"number {LIST}/{m}/marker/level {round(mk.get('level', 0.0), 3)}")
        self.send(f"color {LIST}/{m}/marker/color {mk.get('color') or DEFAULT_COLOR}")

    def show_ha_state(self, m: int, state: dict):
        """a Home Assistant light state (from /api/states or a state_changed
        event) → light m's level and colour"""
        attrs = state.get("attributes", {})
        if state.get("state") != "on":
            level = 0.0
        else:
            level = (attrs.get("brightness") or 255) / 255
        rgb = attrs.get("rgb_color")
        color = "#{:02X}{:02X}{:02X}".format(*rgb) if rgb and len(rgb) == 3 else None
        with self.lock:
            mk = self.markers[m]
            if mk.get("level") != level or mk.get("color") != color:
                mk["level"], mk["color"] = level, color
                self._show_state(m)

    def _icon(self, m: int) -> int:
        if self.edit:
            return ICON_MOVE
        return ICON_BULB if self.markers[m].get("entities") else ICON_NOT_CONNECTED

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
        for prop in ("x", "y", "press"):
            self.send(f"watch {LIST}/{m}/{prop}")
        self._show(m)
        self._show_edit_item(m)
        self._show_state(m)
        if m == self.selected:
            self.send(f"number {LIST}/{m}/marker/selected 1")

    def _show(self, m: int):
        self.send(f"number {LIST}/{m}/x {self.markers[m]['x'] - SIZE / 2}")
        self.send(f"number {LIST}/{m}/y {self.markers[m]['y'] - SIZE / 2}")

    def _show_edit(self):
        self.send(f"number lights/edit {1 if self.edit else 0}")
        self.send(f"number lights/scroll {0 if self.edit else 1}")

    def _show_edit_item(self, m: int):
        self.send(f"number {LIST}/{m}/edit {1 if self.edit else 0}")
        self.send(f"number {LIST}/{m}/marker/icon {self._icon(m)}")

    def _load(self) -> list[dict]:
        try:
            markers = json.loads(STORE.read_text()).get("markers", [])
        except (OSError, json.JSONDecodeError, AttributeError):
            return []
        lights = []
        for m in markers:
            if not isinstance(m, dict):
                continue
            m = {**m, "x": float(m.get("x", PLAN_W / 2)), "y": float(m.get("y", PLAN_H / 2))}
            if "on" in m:                         # saved before level existed
                m.setdefault("level", 1.0 if m.pop("on") else 0.0)
            lights.append(m)
        return lights

    def _save(self):
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"markers": self.markers}, indent=2))
            tmp.replace(STORE)
        except OSError as e:
            self.log(f"lights: cannot save {STORE} ({e})")
