"""The Lights app (homy-neo-hmi's LightsApp): lights placed on the floorplan.

Rive only draws and reports touches; everything else is here. Each touchable
thing has a `press` number the file writes: 1 finger down, 0 finger up on it,
2 finger slid off (cancelled).

  add-light button      a new light at the middle of the plan, being moved,
                        with its settings open
  a light, not set up   tap: its settings (which Home Assistant lights it is)
  a light, set up       tap (released before LONG_PRESS): on/off
                        hold: the adjust panel (brightness, colour/temperature)
  settings panel        the move switch (drag on the plan to place the light),
                        the list of Home Assistant lights (tap: in/out), close
  adjust panel          brightness ring, colour wheel or temperature ring
                        (the switch beside them picks), close

The placed lights are kept in ~/.config/homy/lights.json:
  {"markers": [{"x": 375, "y": 176, "entities": ["light.ceiling"], "mode": 0}, …]}
x/y: the light's centre on the floorplan (750 × 353), slot = position in the list.

  here → homy-hmi   number lights/floorplan/marker3X 245     the marker's top left
                    number lights/floorplan/marker3/lit 1     on (gold ring)
                    number lights/panel 1                     0 none, 1 settings, 2 adjust
                    string lights/settings/row2/label Ceiling
  homy-hmi → here   number lights/floorplan/marker3/press 1   (watched)
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

from light_client import HAClient, LightSender

SECRETS = Path.home() / ".config" / "home-app" / "secrets.json"
STORE = Path.home() / ".config" / "homy" / "lights.json"

MARKERS = 10            # marker slots in the file (FloorPlan: marker0 … marker9)
ROWS = 16               # rows in the settings list (SettingsPanel: row0 … row15)
MARKER_SIZE = 100       # the LightMarker artboard; its x/y are its top left
PLAN_W, PLAN_H = 750, 353
HIDDEN = -200           # a free slot sits outside the plan
LONG_PRESS = 0.5        # s: holding a light this long opens the adjust panel
POLL = 3.0              # s: how often the lights' on/off state is read
SETTLED = 0.4           # s: a ring or the wheel unchanged this long counts as let go

WHEEL_C, WHEEL_R = 90, 78           # ColorWheel: centre, radius of full saturation (ColorWheel.png)
WHEEL_KNOB_MAX = 80                 # the knob stays inside the wheel
HUE_AT_TOP = -135                   # the wheel's hue straight up (red sits bottom right)
WARM_K, COLD_K = 2200, 6500         # temperature ring: 0 cold (blue) … 1 warm (orange)

PANEL_NONE, PANEL_SETTINGS, PANEL_ADJUST = 0, 1, 2
MODE_COLOR, MODE_TEMPERATURE = 0, 1


class Lights:
    def __init__(self, send, log):
        self.send, self.log = send, log
        try:
            secrets = json.loads(SECRETS.read_text())
        except (OSError, json.JSONDecodeError):
            secrets = {}
        self.ha = HAClient(secrets.get("ha_url", "http://localhost:8123"), secrets.get("ha_token", ""))
        self.sender = LightSender(self.ha, final_only=secrets.get("lights_final_only", []),
                                  log=lambda msg: log(f"lights: {msg}"))
        self.lock = threading.RLock()
        self.markers: list[dict] = self._load()
        self.available: list[dict] = []          # Home Assistant's lights: {"entity_id", "name"}
        self.states: dict[str, dict] = {}        # entity → its state (from the last poll)
        self.lines: dict[str, str] = {}          # path → last line, replayed when homy-hmi restarts
        self.pressed: dict[str, float] = {}      # press path → when the finger went down
        self.long_timer: threading.Timer | None = None
        self.long_fired = False
        self.panel = PANEL_NONE
        self.current: int | None = None          # the marker the open panel is about
        self.moving = False
        self.change: dict = {}                   # the adjust panel's last change, sent as final once it settles
        self.change_timer: threading.Timer | None = None

    # ── setup ────────────────────────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._poll, daemon=True).start()

    def ready(self):
        """homy-hmi (re)started: watch the touchables, replay what it shows."""
        watched = ["lights/add", "lights/floorplan/cursorX", "lights/floorplan/cursorY",
                   "lights/settings/move/press", "lights/settings/close/press",
                   "lights/adjust/close/press", "lights/adjust/modeSwitch/press",
                   "lights/adjust/brightness/value", "lights/adjust/temperature/value",
                   "lights/adjust/wheel/x", "lights/adjust/wheel/y"]
        watched += [f"lights/floorplan/marker{m}/press" for m in range(MARKERS)]
        watched += [f"lights/settings/row{r}/press" for r in range(ROWS)]
        for path in watched:
            self.send(f"watch {path}")
        with self.lock:
            if self.lines:
                for line in list(self.lines.values()):
                    self.send(line)
            else:
                self._show_all()

    def _set(self, kind: str, path: str, value):
        if isinstance(value, float):
            value = round(value, 3)
        line = f"{kind} {path} {value}"
        if self.lines.get(path) != line:
            self.lines[path] = line
            self.send(line)

    # ── the store ────────────────────────────────────────────────────────────
    def _load(self) -> list[dict]:
        try:
            markers = json.loads(STORE.read_text()).get("markers", [])
        except (OSError, json.JSONDecodeError, AttributeError):
            return []
        return [{"x": float(m.get("x", PLAN_W / 2)), "y": float(m.get("y", PLAN_H / 2)),
                 "entities": list(m.get("entities", [])), "mode": int(m.get("mode", MODE_COLOR))}
                for m in markers if isinstance(m, dict)][:MARKERS]

    def _save(self):
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"markers": self.markers}, indent=2))
            tmp.replace(STORE)
        except OSError as e:
            self.log(f"lights: cannot save {STORE} ({e})")

    # ── to the page ──────────────────────────────────────────────────────────
    def _show_all(self):
        for m in range(MARKERS):
            self._show_marker(m)
        self._show_panel()

    def _show_marker(self, m: int):
        base = f"lights/floorplan/marker{m}"
        if m < len(self.markers):
            mk = self.markers[m]
            self._set("number", base + "X", mk["x"] - MARKER_SIZE / 2)
            self._set("number", base + "Y", mk["y"] - MARKER_SIZE / 2)
            self._set("number", base + "/icon", 1 if self.moving and m == self.current else 0)
            self._set("number", base + "/lit", 1 if self._is_on(mk) else 0)
        else:
            self._set("number", base + "X", HIDDEN)
            self._set("number", base + "Y", HIDDEN)

    def _show_panel(self):
        self._set("number", "lights/panel", self.panel)
        self._set("number", "lights/scroll", 0 if self.panel != PANEL_NONE or self.moving else 1)
        self._set("number", "lights/floorplan/moving", 1 if self.moving else 0)
        self._set("number", "lights/settings/move/on", 1 if self.moving else 0)
        if self.panel == PANEL_SETTINGS:
            self._show_rows()

    def _show_rows(self):
        mine = set(self.markers[self.current]["entities"]) if self.current is not None else set()
        rows = self.available[:ROWS]
        self._set("number", "lights/settings/rows", len(rows))
        for r, light in enumerate(rows):
            self._set("string", f"lights/settings/row{r}/label", light["name"])
            self._set("number", f"lights/settings/row{r}/selected", 1 if light["entity_id"] in mine else 0)

    def _show_mode(self):
        mode = self.markers[self.current]["mode"]
        self._set("number", "lights/adjust/mode", mode)
        self._set("number", "lights/adjust/modeSwitch/on", mode)

    def _show_adjust(self):
        """the adjust panel's controls from the marker's first light"""
        mk = self.markers[self.current]
        self._show_mode()
        state = self.states.get(mk["entities"][0], {}) if mk["entities"] else {}
        attrs = state.get("attributes", {})
        on = state.get("state") == "on"
        self._set("number", "lights/adjust/brightness/value", (attrs.get("brightness") or 255) / 255 if on else 0.0)
        kelvin = attrs.get("color_temp_kelvin")
        if kelvin:
            self._set("number", "lights/adjust/temperature/value", (COLD_K - kelvin) / (COLD_K - WARM_K))
        hs = attrs.get("hs_color")
        if hs:
            x, y = wheel_point(float(hs[0]), float(hs[1]) / 100)
            self._set("number", "lights/adjust/wheel/x", x)
            self._set("number", "lights/adjust/wheel/y", y)

    def _is_on(self, mk: dict) -> bool:
        return any(self.states.get(e, {}).get("state") == "on" for e in mk["entities"])

    # ── from the page ────────────────────────────────────────────────────────
    def on_number(self, path: str, value: float) -> bool:
        if not path.startswith("lights/"):
            return False
        with self.lock:
            self.lines[path] = f"number {path} {round(value, 3) if value != int(value) else int(value)}"
            parts = path.split("/")
            if path == "lights/add":
                if self._released(path, value):
                    self._add()
            elif parts[1] == "floorplan" and parts[2].startswith("marker") and parts[-1] == "press":
                self._marker_press(int(parts[2][6:]), path, value)
            elif path in ("lights/floorplan/cursorX", "lights/floorplan/cursorY"):
                self._cursor()
            elif parts[1] == "settings" and parts[2].startswith("row"):
                if self._released(path, value):
                    self._toggle_entity(int(parts[2][3:]))
            elif path == "lights/settings/move/press":
                if self._released(path, value) and self.current is not None:
                    self.moving = not self.moving
                    self._show_marker(self.current)
                    self._show_panel()
            elif path in ("lights/settings/close/press", "lights/adjust/close/press"):
                if self._released(path, value):
                    self._close()
            elif path == "lights/adjust/modeSwitch/press":
                if self._released(path, value) and self.current is not None:
                    mk = self.markers[self.current]
                    mk["mode"] = MODE_TEMPERATURE if mk["mode"] == MODE_COLOR else MODE_COLOR
                    self._save()
                    self._show_mode()
            elif path == "lights/adjust/brightness/value":
                self._adjust(brightness=max(0.0, min(1.0, value)))
            elif path == "lights/adjust/temperature/value":
                self._adjust(kelvin=COLD_K - max(0.0, min(1.0, value)) * (COLD_K - WARM_K))
            elif path in ("lights/adjust/wheel/x", "lights/adjust/wheel/y"):
                self._wheel()
            else:
                self.log(f"lights: {path} {value}")
        return True

    def _released(self, path: str, value: float) -> bool:
        """a tap: the finger went down and came up on it"""
        if value == 1:
            self.pressed[path] = time.monotonic()
            return False
        return self.pressed.pop(path, None) is not None and value == 0

    def _current_entities(self) -> list[str]:
        return list(self.markers[self.current]["entities"]) if self.current is not None else []

    def _add(self):
        if len(self.markers) >= MARKERS:
            self.log(f"lights: all {MARKERS} light places are used")
            return
        self.markers.append({"x": PLAN_W / 2, "y": PLAN_H / 2, "entities": [], "mode": MODE_COLOR})
        self._save()
        self._open(len(self.markers) - 1, PANEL_SETTINGS, moving=True)

    def _open(self, m: int, panel: int, moving: bool = False):
        previous, self.current = self.current, m
        self.panel, self.moving = panel, moving
        if previous is not None and previous != m:
            self._show_marker(previous)
        self._show_marker(m)
        self._show_panel()
        if panel == PANEL_SETTINGS:
            threading.Thread(target=self._refresh_available, daemon=True).start()
        elif panel == PANEL_ADJUST:
            self._show_adjust()

    def _close(self):
        m = self.current
        self.panel, self.moving, self.current = PANEL_NONE, False, None
        self._save()
        if m is not None:
            self._show_marker(m)
        self._show_panel()

    def _marker_press(self, m: int, path: str, value: float):
        if m >= len(self.markers):
            return
        mk = self.markers[m]
        if value == 1:
            self.pressed[path] = time.monotonic()
            self.long_fired = False
            if self.long_timer:
                self.long_timer.cancel()
            if mk["entities"]:
                self.long_timer = threading.Timer(LONG_PRESS, self._long_press, (m, path))
                self.long_timer.start()
            return
        if self.long_timer:
            self.long_timer.cancel()
            self.long_timer = None
        down = self.pressed.pop(path, None)
        if value != 0 or down is None or self.long_fired:
            return                                  # slid off, or the hold already opened the panel
        if self.moving and m == self.current:
            return                                  # being placed: touches move it
        if not mk["entities"]:
            self._open(m, PANEL_SETTINGS)
        else:
            self._toggle_light(m)

    def _long_press(self, m: int, path: str):
        with self.lock:
            if path in self.pressed and m < len(self.markers):
                self.long_fired = True
                self._open(m, PANEL_ADJUST)

    def _toggle_light(self, m: int):
        mk = self.markers[m]
        service = "turn_off" if self._is_on(mk) else "turn_on"
        for e in mk["entities"]:                    # show it at once; the next poll confirms
            self.states.setdefault(e, {})["state"] = "on" if service == "turn_on" else "off"
        self._show_marker(m)
        threading.Thread(target=self.ha.call_service, args=("light", service, {"entity_id": mk["entities"]}),
                         daemon=True).start()

    def _toggle_entity(self, row: int):
        if self.current is None or row >= len(self.available):
            return
        entities = self.markers[self.current]["entities"]
        e = self.available[row]["entity_id"]
        entities.remove(e) if e in entities else entities.append(e)
        self._save()
        self._show_rows()
        self._show_marker(self.current)

    def _cursor(self):
        """moving a light: it follows the finger on the plan"""
        if not self.moving or self.current is None:
            return
        x = number(self.lines.get("lights/floorplan/cursorX"), PLAN_W / 2)
        y = number(self.lines.get("lights/floorplan/cursorY"), PLAN_H / 2)
        mk = self.markers[self.current]
        mk["x"] = max(MARKER_SIZE / 2, min(PLAN_W - MARKER_SIZE / 2, x))
        mk["y"] = max(MARKER_SIZE / 2, min(PLAN_H - MARKER_SIZE / 2, y))
        self._show_marker(self.current)

    def _wheel(self):
        x = number(self.lines.get("lights/adjust/wheel/x"), WHEEL_C)
        y = number(self.lines.get("lights/adjust/wheel/y"), WHEEL_C)
        dx, dy = x - WHEEL_C, y - WHEEL_C
        r = math.hypot(dx, dy)
        if r > WHEEL_KNOB_MAX:                      # back inside the wheel
            dx, dy = dx * WHEEL_KNOB_MAX / r, dy * WHEEL_KNOB_MAX / r
            self._set("number", "lights/adjust/wheel/x", WHEEL_C + dx)
            self._set("number", "lights/adjust/wheel/y", WHEEL_C + dy)
        hue = (math.degrees(math.atan2(dx, -dy)) + HUE_AT_TOP) % 360
        sat = min(1.0, math.hypot(dx, dy) / WHEEL_R)
        self._adjust(hs=(hue, sat))

    def _adjust(self, **change):
        """a ring or the wheel moved: a step now (LightSender paces and fades
        them), and the same value as final once the finger has let go — the
        rings and the wheel report no release, so: once nothing changed for
        SETTLED seconds"""
        entities = self._current_entities()
        for e in entities:
            self.sender.update(e, **change)
        if "brightness" in change:
            self.change["brightness"] = change["brightness"]
        for key in ("hs", "kelvin"):
            if key in change:
                self.change.pop("hs", None), self.change.pop("kelvin", None)
                self.change[key] = change[key]
        if self.change_timer:
            self.change_timer.cancel()
        self.change_timer = threading.Timer(SETTLED, self._settled, (entities,))
        self.change_timer.start()

    def _settled(self, entities: list[str]):
        with self.lock:
            change, self.change = self.change, {}
        for e in entities:
            self.sender.update(e, final=True, **change)

    # ── from Home Assistant ──────────────────────────────────────────────────
    def _refresh_available(self):
        states = self.ha.get_states()
        if states is None:
            return
        with self.lock:
            self._take_states(states)
            if self.panel == PANEL_SETTINGS:
                self._show_rows()

    def _take_states(self, states: list[dict]):
        lights = [s for s in states if s.get("entity_id", "").startswith("light.")]
        self.states = {s["entity_id"]: s for s in lights}
        self.available = sorted(({"entity_id": s["entity_id"],
                                  "name": s.get("attributes", {}).get("friendly_name", s["entity_id"])}
                                 for s in lights), key=lambda l: l["name"].lower())

    def _poll(self):
        while True:
            states = self.ha.get_states()
            if states is not None:
                with self.lock:
                    self._take_states(states)
                    for m in range(len(self.markers)):
                        self._set("number", f"lights/floorplan/marker{m}/lit", 1 if self._is_on(self.markers[m]) else 0)
            time.sleep(POLL)


def number(line: str | None, default: float) -> float:
    try:
        return float(line.rsplit(" ", 1)[1]) if line else default
    except (IndexError, ValueError):
        return default


def wheel_point(hue: float, sat: float) -> tuple[float, float]:
    """where on the ColorWheel a colour sits (the inverse of Lights._wheel)"""
    angle = math.radians(hue - HUE_AT_TOP)
    r = min(sat, 1.0) * WHEEL_R
    return WHEEL_C + r * math.sin(angle), WHEEL_C - r * math.cos(angle)
