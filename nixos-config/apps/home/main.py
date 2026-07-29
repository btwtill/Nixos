import sys
import threading
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

from widgets.arc_slider     import ArcSlider
from widgets.weather        import WeatherWidget
from widgets.music_controls import MusicControls
from ha_client               import HAClient
import config

# Canvas dimensions (px)
W, H    = 814, 490
LEFT_W  = 521
RIGHT_W = W - LEFT_W   # 293
ROW_H   = H // 2       # 245


class HomeWidget(QWidget):
    """Root widget — places the four sections using absolute geometry."""

    _brightness_polled = pyqtSignal(float)
    _weather_polled    = pyqtSignal(object)   # emits {condition, attrs, forecast}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        assets = config.ASSETS

        # ── Top-left: weather dashboard ───────────────────────────────────────
        self._weather = WeatherWidget(assets, parent=self)
        self._weather.setGeometry(0, 0, LEFT_W, ROW_H)

        # ── Top-right: brightness arc slider ─────────────────────────────────
        ls = config.LIGHT_SLIDER
        self._light_sl = ArcSlider(
            center       = ls.center,
            radius       = ls.radius,
            start_angle  = ls.start_angle,
            end_angle    = ls.end_angle,
            clockwise    = ls.clockwise,
            track_width  = ls.track_width,
            track_color  = ls.track_color,
            fill_color   = ls.fill_color,
            bg_image     = str(assets / ls.bg_image)     if ls.bg_image     else "",
            handle_image = str(assets / ls.handle_image) if ls.handle_image else "",
            handle_size  = ls.handle_size,
            bg_offset    = ls.bg_offset,
            parent=self,
        )
        self._light_sl.setGeometry(LEFT_W, 0, RIGHT_W, ROW_H)

        # ── Bottom-left: music controls ───────────────────────────────────────
        self._music = MusicControls(assets, parent=self)
        self._music.setGeometry(0, ROW_H, LEFT_W, ROW_H)

        # ── Bottom-right: temperature arc slider ──────────────────────────────
        ts = config.TEMP_SLIDER
        self._temp_sl = ArcSlider(
            center       = ts.center,
            radius       = ts.radius,
            start_angle  = ts.start_angle,
            end_angle    = ts.end_angle,
            clockwise    = ts.clockwise,
            track_width  = ts.track_width,
            track_color  = ts.track_color,
            fill_color   = ts.fill_color,
            bg_image     = str(assets / ts.bg_image)     if ts.bg_image     else "",
            handle_image = str(assets / ts.handle_image) if ts.handle_image else "",
            handle_size  = ts.handle_size,
            bg_offset    = ts.bg_offset,
            parent=self,
        )
        self._temp_sl.setGeometry(LEFT_W, ROW_H, RIGHT_W, ROW_H)

        # ── Wire signals ──────────────────────────────────────────────────────
        self._light_sl.value_changed.connect(self._on_brightness)
        self._temp_sl.value_changed.connect(self._on_temperature)
        self._music.control_pressed.connect(self._on_music_ctrl)
        self._music.seek_changed.connect(self._on_seek)

        # ── Home Assistant ─────────────────────────────────────────────────────
        self._ha = HAClient(config.HA_URL, config.HA_TOKEN)

        # Brightness slider ↔ HA light
        self._brightness_polled.connect(self._apply_polled_brightness)
        self._pending_brightness = 0.0
        self._brightness_debounce = QTimer(self)
        self._brightness_debounce.setSingleShot(True)
        self._brightness_debounce.setInterval(150)
        self._brightness_debounce.timeout.connect(self._send_brightness)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(config.HA_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_light_state)
        self._poll_timer.start()
        self._poll_light_state()

        # Weather
        self._weather_polled.connect(self._apply_weather)
        self._weather_timer = QTimer(self)
        self._weather_timer.setInterval(config.WEATHER_POLL_INTERVAL_MS)
        self._weather_timer.timeout.connect(self._poll_weather)
        self._weather_timer.start()
        self._poll_weather()

    def _on_brightness(self, value: float):
        self._pending_brightness = value
        self._brightness_debounce.start()

    def _send_brightness(self):
        pct = round(self._pending_brightness * 100)
        threading.Thread(
            target=self._ha.set_light_brightness,
            args=(config.LIGHT_ENTITY, pct),
            daemon=True,
        ).start()

    def _poll_light_state(self):
        threading.Thread(target=self._poll_light_state_worker, daemon=True).start()

    def _poll_light_state_worker(self):
        pct = self._ha.get_light_brightness_pct(config.LIGHT_ENTITY)
        if pct is not None:
            self._brightness_polled.emit(pct)

    def _apply_polled_brightness(self, pct: float):
        if not self._light_sl.is_dragging:
            self._light_sl.set_value_silent(pct)

    # ── weather ───────────────────────────────────────────────────────────────

    def _poll_weather(self):
        threading.Thread(target=self._poll_weather_worker, daemon=True).start()

    def _poll_weather_worker(self):
        import os, datetime
        state    = self._ha.get_weather_state(config.WEATHER_ENTITY)
        forecast = self._ha.get_weather_forecast(config.WEATHER_ENTITY)
        log_dir  = os.path.expanduser("~/.local/share/home-app")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "weather_debug.log"), "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()} "
                    f"condition={state.get('state') if state else None} "
                    f"forecast_slots={len(forecast) if forecast else 0} "
                    f"forecast_sample={forecast[0] if forecast else None} "
                    f"fc_raw={getattr(self._ha, '_last_forecast_raw', '(no attr)')}\n")
        if state is not None:
            self._weather_polled.emit({
                "condition": state.get("state", ""),
                "attrs":     state.get("attributes", {}),
                "forecast":  forecast or [],
            })

    def _apply_weather(self, data: dict):
        self._weather.update_weather(
            condition = data["condition"],
            attrs     = data["attrs"],
            forecast  = data["forecast"],
        )

    def _on_temperature(self, value: float):
        low, high = 16.0, 26.0
        temp = low + value * (high - low)
        # TODO: set thermostat target
        print(f"[temperature] {temp:.1f} °C")

    def _on_music_ctrl(self, action: str):
        # TODO: forward to controls module (same dbus calls as the music app)
        print(f"[music]       {action}")

    def _on_seek(self, t: float):
        # TODO: seek track
        print(f"[seek]        {t:.1%}")


class HomeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Home")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(HomeWidget())
        self.setFixedSize(W, H)


def main():
    print("[home-app] starting", flush=True)
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Home")
        print("[home-app] QApplication created", flush=True)
        window = HomeApp()
        print("[home-app] window created", flush=True)
        window.show()
        print("[home-app] window shown — entering event loop", flush=True)
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
