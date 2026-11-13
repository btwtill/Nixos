"""The Home page of the HMI (HomeApp in homy-neo-hmi.riv) ↔ the house.

The page is drawn and animated by the Rive file; this module only feeds it and
acts on what it reports, through HMIInterface/home:

  here → homy-hmi   number home/light/value 0.6      the light's brightness
                    string home/weather/temperature  "23°"
                    string home/hour3/hour|temp      the hourly forecast
                    number home/sensor/level 0.4     for the sensor's current mode
                    number home/playIcon 1|2         play / pause glyph
  homy-hmi → here   number home/light/value …        the ring was dragged
                    number home/sensor/mode 0…3      the sensor tile was tapped
                    number home/mediaAction 1|2|3    previous / play-pause / next

Home Assistant connection: ~/.config/home-app/secrets.json, as for the old
home-app (ha_url, ha_token, weather_entity, light_entity).
"""
from __future__ import annotations

import datetime
import json
import threading
import time
from pathlib import Path

import airplay
from ha_client import HAClient

SECRETS = Path.home() / ".config" / "home-app" / "secrets.json"
LIGHT_POLL_S, WEATHER_POLL_S = 3, 60
MEDIA_ACTIONS = {1: "prev", 2: "play_pause", 3: "next"}
WATCHED = ("home/light/value", "home/climate/value", "home/sensor/mode", "home/mediaAction")


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# sensor tile mode → (weather attribute, value shown as empty, value shown as full)
SENSOR = {0: ("temperature", -10, 40), 1: ("wind_speed", 0, 60), 2: ("pressure", 970, 1040), 3: ("humidity", 0, 100)}


class Home:
    def __init__(self, send, log):
        self.send, self.log = send, log
        try:
            secrets = json.loads(SECRETS.read_text())
        except (OSError, json.JSONDecodeError):
            secrets = {}
        self.ha = HAClient(secrets.get("ha_url", "http://localhost:8123"), secrets.get("ha_token", ""))
        self.light = secrets.get("light_entity", "light.h60a6")
        self.weather = secrets.get("weather_entity", "weather.forecast_home")
        self.mode = 0
        self.attrs: dict = {}                    # the weather entity's attributes
        self.lines: dict[str, str] = {}          # path → last line sent, replayed when homy-hmi restarts
        self.touched = 0.0                       # when the light ring was last dragged
        self.pending: threading.Timer | None = None

    def start(self):
        threading.Thread(target=self._poll_light, daemon=True).start()
        threading.Thread(target=self._poll_weather, daemon=True).start()
        airplay.AirPlayWatcher(lambda info: self._set("number", "home/playIcon", 2 if info.playing else 1)).start()

    def ready(self):
        """homy-hmi (re)started: watch what the page reports, replay what it shows."""
        for path in WATCHED:
            self.send(f"watch {path}")
        for line in list(self.lines.values()):
            self.send(line)

    def _set(self, kind: str, path: str, value):
        line = f"{kind} {path} {value}"
        if self.lines.get(path) != line:
            self.lines[path] = line
            self.send(line)

    # ── from the page ────────────────────────────────────────────────────────
    def on_number(self, path: str, value: float) -> bool:
        if path == "home/light/value":
            self.touched = time.monotonic()
            if self.pending:
                self.pending.cancel()            # while dragging: only the last value goes out
            self.pending = threading.Timer(0.15, self.ha.set_light_brightness, (self.light, round(value * 100)))
            self.pending.start()
        elif path == "home/climate/value":
            self.log(f"thermostat: {16 + value * 10:.1f} °C (not connected yet)")
        elif path == "home/sensor/mode":
            self.mode = int(value)
            self._sensor_level()
        elif path == "home/mediaAction":
            if int(value) in MEDIA_ACTIONS:
                airplay.run_action(MEDIA_ACTIONS[int(value)])
            self.send("number home/mediaAction 0")   # armed for the next tap
        else:
            return False
        return True

    # ── to the page ──────────────────────────────────────────────────────────
    def _poll_light(self):
        while True:
            pct = self.ha.get_light_brightness_pct(self.light)
            if pct is not None and time.monotonic() - self.touched > 2:   # not against a finger on the ring
                self._set("number", "home/light/value", round(pct, 3))
            time.sleep(LIGHT_POLL_S)

    def _sensor_level(self):
        attribute, low, high = SENSOR.get(self.mode, SENSOR[0])
        value = self.attrs.get(attribute)
        if isinstance(value, (int, float)):
            self._set("number", "home/sensor/level", round(_clamp((value - low) / (high - low)), 3))

    def _poll_weather(self):
        while True:
            state = self.ha.get_weather_state(self.weather)
            if state is None:
                time.sleep(5)                    # Home Assistant not up yet
                continue
            self.attrs = state.get("attributes", {})
            temperature = self.attrs.get("temperature")
            if isinstance(temperature, (int, float)):
                self._set("string", "home/weather/temperature", f"{round(temperature)}°")
            self._sensor_level()
            slots = self.ha.get_weather_forecast(self.weather) or []
            now = datetime.datetime.now().astimezone()
            shown = 0
            for slot in slots:
                try:
                    at = datetime.datetime.fromisoformat(slot.get("datetime", "")).astimezone()
                except ValueError:
                    continue
                if at < now - datetime.timedelta(hours=1) or shown >= 8:
                    continue
                self._set("string", f"home/hour{shown}/hour", at.strftime("%H"))
                if isinstance(slot.get("temperature"), (int, float)):
                    self._set("string", f"home/hour{shown}/temp", f"{round(slot['temperature'])}°")
                shown += 1
            time.sleep(WEATHER_POLL_S)
