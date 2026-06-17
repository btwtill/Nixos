import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

from widgets.arc_slider     import ArcSlider
from widgets.floorplan      import FloorplanWidget
from widgets.music_controls import MusicControls
import config

# Canvas dimensions (px)
W, H    = 814, 490
LEFT_W  = 521
RIGHT_W = W - LEFT_W   # 293
ROW_H   = H // 2       # 245


class HomeWidget(QWidget):
    """Root widget — places the four sections using absolute geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        assets = config.ASSETS

        # ── Top-left: floorplan with light buttons ────────────────────────────
        self._floor = FloorplanWidget(config.LIGHTS, assets, parent=self)
        self._floor.setGeometry(0, 0, LEFT_W, ROW_H)

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
            parent=self,
        )
        self._temp_sl.setGeometry(LEFT_W, ROW_H, RIGHT_W, ROW_H)

        # ── Wire signals ──────────────────────────────────────────────────────
        self._floor.light_toggled.connect(self._on_light_toggle)
        self._light_sl.value_changed.connect(self._on_brightness)
        self._temp_sl.value_changed.connect(self._on_temperature)
        self._music.control_pressed.connect(self._on_music_ctrl)
        self._music.seek_changed.connect(self._on_seek)

    # ── Handlers — wire to your home-automation backend here ─────────────────

    def _on_light_toggle(self, name: str, on: bool):
        # TODO: publish to Home Assistant / MQTT
        print(f"[light]       {name!r} → {'on' if on else 'off'}")

    def _on_brightness(self, value: float):
        # TODO: set light brightness (0-100)
        print(f"[brightness]  {value:.0%}")

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
