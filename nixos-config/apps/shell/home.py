"""The Home page of the HMI (HomeApp in homy-neo-hmi.riv) ↔ the house.

The page is drawn and animated by the Rive file; this module only feeds it and
acts on what it reports, through HMIInterface/home:

  here → homy-hmi   number home/light/value 0.6               the light's brightness
                    string home/attribute/value "23°"         the shown attribute's value
                    number home/attribute/level 0.4           … as 0…1 (for a gauge)
                    number home/weather/condition 11          the weather now (CONDITIONS)
                    string home/forecast/hour3/hour|temp      the hourly forecast: 24 columns,
                    number home/forecast/hour3/icon 8         PAST_HOURS ago … 17 hours ahead
                    number home/forecast/center 6             the column scrolled to the middle
                    number home/playIcon 1|2                  play / pause glyph
  homy-hmi → here   number home/light/value …                 the ring was dragged
                    number home/attribute/mode 0…3            the attribute was tapped
                    number home/mediaAction 1|2|3             previous / play-pause / next

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
# Home Assistant only forecasts ahead: what it said about each hour is kept, so
# the forecast can also be scrolled into the hours that have passed.
FORECAST_CACHE = Path.home() / ".local" / "state" / "homy-shell" / "forecast.json"
FORECAST_COLUMNS, PAST_HOURS = 24, 6
LIGHT_POLL_S, WEATHER_POLL_S = 3, 60
MEDIA_ACTIONS = {1: "prev", 2: "play_pause", 3: "next"}
WATCHED = ("home/light/value", "home/climate/value", "home/attribute/mode", "home/mediaAction")


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# Home Assistant weather condition → the state in the Rive file: the order of
# the children of WeatherState's "Conditions" Solo and ForecastHour's "Condition"
# Solo (homy-design: Figma_Assets/WeatherIcons, one state each).
CONDITIONS = {
    "clear-night": 0, "cloudy": 1, "fog": 2, "hail": 3, "lightning": 4, "lightning-rainy": 5,
    "partlycloudy": 6, "pouring": 7, "rainy": 8, "snowy": 9, "snowy-rainy": 10, "sunny": 11,
    "windy": 12, "windy-variant": 12,
    "exceptional": 1,   # no icon of its own
}
NO_CONDITION = 13       # ForecastHour's empty state: an hour nothing is known about

# WeatherAttribute mode (the icon shown) → (weather entity attribute, low, high
# for the 0…1 level, how the value is written)
ATTRIBUTES = {
    0: ("temperature", -10, 40, lambda v: f"{round(v)}°"),
    1: ("wind_speed", 0, 60, lambda v: f"{round(v)}"),      # km/h, Home Assistant's default unit
    2: ("pressure", 970, 1040, lambda v: f"{round(v)}"),     # hPa
    3: ("humidity", 0, 100, lambda v: f"{round(v)}%"),
}


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
        self.forecast = self._load_forecast()    # "YYYY-MM-DDTHH" → {"temperature": …, "condition": …}
        self.forecast_hour = ""                  # the hour the columns were last laid out for
        self.centered = 0.0

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
        elif path == "home/attribute/mode":
            self.mode = int(value)
            self._attribute()
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

    def _attribute(self):
        """The value of the attribute the page shows (temperature, wind, …)."""
        attribute, low, high, text = ATTRIBUTES.get(self.mode, ATTRIBUTES[0])
        value = self.attrs.get(attribute)
        if isinstance(value, (int, float)):
            self._set("string", "home/attribute/value", text(value))
            self._set("number", "home/attribute/level", round(_clamp((value - low) / (high - low)), 3))
        else:
            self._set("string", "home/attribute/value", "–")

    # ── forecast ─────────────────────────────────────────────────────────────
    def recenter(self):
        """Scroll the forecast back to the current hour (also after the user scrolled away)."""
        # The file only takes over a value that changed: alternate between two
        # that both put the current hour in the middle.
        self.centered = PAST_HOURS + (0.0001 if self.centered == PAST_HOURS else 0)
        line = f"number home/forecast/center {self.centered}"
        self.lines["home/forecast/center"] = line
        self.send(line)

    def _load_forecast(self) -> dict:
        try:
            return json.loads(FORECAST_CACHE.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_forecast(self):
        try:
            FORECAST_CACHE.parent.mkdir(parents=True, exist_ok=True)
            FORECAST_CACHE.write_text(json.dumps(self.forecast))
        except OSError as e:
            self.log(f"forecast cache: {e}")

    def _show_forecast(self, slots: list):
        now = datetime.datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
        for slot in slots:   # newest forecast wins, older hours stay as they were forecast
            try:
                at = datetime.datetime.fromisoformat(slot.get("datetime", "")).astimezone()
            except ValueError:
                continue
            self.forecast[at.strftime("%Y-%m-%dT%H")] = {
                "temperature": slot.get("temperature"), "condition": slot.get("condition")}
        oldest = (now - datetime.timedelta(hours=PAST_HOURS + 24)).strftime("%Y-%m-%dT%H")
        self.forecast = {k: v for k, v in self.forecast.items() if k >= oldest}
        self._save_forecast()
        for column in range(FORECAST_COLUMNS):
            at = now + datetime.timedelta(hours=column - PAST_HOURS)
            known = self.forecast.get(at.strftime("%Y-%m-%dT%H"), {})
            temperature = known.get("temperature")
            self._set("string", f"home/forecast/hour{column}/hour", at.strftime("%H"))
            self._set("string", f"home/forecast/hour{column}/temp",
                      f"{round(temperature)}°" if isinstance(temperature, (int, float)) else "–")
            self._set("number", f"home/forecast/hour{column}/icon", CONDITIONS.get(known.get("condition"), NO_CONDITION))
        if now.strftime("%Y-%m-%dT%H") != self.forecast_hour:   # a new hour: the columns moved by one
            self.forecast_hour = now.strftime("%Y-%m-%dT%H")
            self.recenter()

    def _poll_weather(self):
        while True:
            state = self.ha.get_weather_state(self.weather)
            if state is None:
                time.sleep(5)                    # Home Assistant not up yet
                continue
            self.attrs = state.get("attributes", {})
            if state.get("state") in CONDITIONS:
                self._set("number", "home/weather/condition", CONDITIONS[state["state"]])
            self._attribute()
            self._show_forecast(self.ha.get_weather_forecast(self.weather) or [])
            time.sleep(WEATHER_POLL_S)
