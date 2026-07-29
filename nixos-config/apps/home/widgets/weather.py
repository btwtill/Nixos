"""Weather dashboard widget — top-left quadrant (521×245 px).

Layout
------
  [216×216 condition icon] | [large number + attribute icon   ]
                           | [      250×90 forecast strip     ]

The attribute block cycles through temperature / humidity / wind / pressure
on a timer (8 s) or when the user clicks anywhere in the right column.
The forecast strip is horizontally scrollable (drag) and auto-centres on
the current hour when data is loaded.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter,
    QColor, QFont, QFontMetricsF, QPixmap,
)
from PyQt6.QtWidgets import QWidget

# ── condition → PNG base name ─────────────────────────────────────────────────

_CONDITION_FILE = {
    "clear-night":     "Dark_Clear-Night",
    "cloudy":          "Dark_Cloudy",
    "exceptional":     "Dark_Exceptional",
    "fog":             "Dark_Fog",
    "hail":            "Dark_Hail",
    "lightning":       "Dark_Lightning",
    "lightning-rainy": "Dark_Lightning-Rainy",
    "partlycloudy":    "Dark_Partly-Cloudy",
    "pouring":         "Dark_Pouring",
    "rainy":           "Dark_Rainy",
    "snowy":           "Dark_Snowy",
    "snowy-rainy":     "Dark_Snowy-Rainy",
    "sunny":           "Dark_Sunny",
    "windy":           "Dark_Windy",
    "windy-variant":   "Dark_Windy",
}

_CONDITION_FALLBACK = {
    "clear-night": ")", "cloudy": "C", "exceptional": "!",
    "fog": "~",         "hail": "·",  "lightning": "↯",
    "lightning-rainy": "↯","partlycloudy": "c","pouring": ":",
    "rainy": "·",       "snowy": "·", "snowy-rainy": "·",
    "sunny": "☀",       "windy": "~", "windy-variant": "~",
}

# (attr key, unit suffix, asset filename)
# No unit suffix — numbers stand alone per design
_METRICS = [
    ("temperature", "",  "Attribute=Temperature.png"),
    ("humidity",    "",  "Attribute=Humidity.png"),
    ("wind_speed",  "",  "Attribute=WindSpeed.png"),
    ("pressure",    "",  "Attribute=Pressure.png"),
]

_FADE_W = 30


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red()   + t * (b.red()   - a.red())),
        int(a.green() + t * (b.green() - a.green())),
        int(a.blue()  + t * (b.blue()  - a.blue())),
    )


class WeatherWidget(QWidget):
    """Condition icon + cycling attribute display + scrollable hourly forecast."""

    _ICON_W   = 216
    _STRIP_H  = 90
    _STRIP_W  = 250
    _SLOT_W   = 42    # fixed px width per slot — enables independent scrolling
    _CYCLE_MS = 8_000

    def __init__(self, assets: Path, parent=None):
        super().__init__(parent)
        self._assets      = assets
        self._condition   = ""
        self._attrs: dict = {}
        self._forecast: list = []
        self._metric_idx  = 0
        self._pix_cache: dict[str, QPixmap | None] = {}
        self._scroll_x: float = 0.0
        self._drag_start_x: float | None = None
        self._drag_scroll_start: float = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(self._CYCLE_MS)
        self._cycle_timer.timeout.connect(self._advance_metric)
        self._cycle_timer.start()

    # ── public API ─────────────────────────────────────────────────────────────

    def update_weather(self, condition: str, attrs: dict, forecast: list):
        self._condition = condition
        self._attrs     = attrs or {}
        self._forecast  = forecast or []
        self._center_on_current_hour()
        self.update()

    # ── scroll ────────────────────────────────────────────────────────────────

    def _center_on_current_hour(self):
        slots = self._forecast
        if not slots:
            self._scroll_x = 0.0
            return
        now_hour = datetime.now().hour
        best_idx, best_diff = 0, float("inf")
        for i, slot in enumerate(slots):
            try:
                dt   = datetime.fromisoformat(slot.get("datetime", ""))
                diff = abs(dt.hour - now_hour)
                if diff < best_diff:
                    best_diff, best_idx = diff, i
            except (ValueError, TypeError):
                pass
        slot_center  = best_idx * self._SLOT_W + self._SLOT_W / 2
        strip_center = self._STRIP_W / 2
        self._scroll_x = max(0.0, min(
            slot_center - strip_center,
            len(slots) * self._SLOT_W - self._STRIP_W,
        ))

    def _clamp_scroll(self):
        max_s = max(0.0, len(self._forecast) * self._SLOT_W - self._STRIP_W)
        self._scroll_x = max(0.0, min(self._scroll_x, max_s))

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        if x > self._ICON_W:
            if y >= self.height() - self._STRIP_H:
                self._drag_start_x      = x
                self._drag_scroll_start = self._scroll_x
            else:
                self._advance_metric()
                self._cycle_timer.start()

    def mouseMoveEvent(self, ev):
        if self._drag_start_x is not None:
            delta = ev.position().x() - self._drag_start_x
            self._scroll_x = self._drag_scroll_start - delta
            self._clamp_scroll()
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start_x = None

    def _advance_metric(self):
        self._metric_idx = (self._metric_idx + 1) % len(_METRICS)
        self.update()

    # ── pixmap helpers ────────────────────────────────────────────────────────

    def _get_pixmap(self, condition: str, size: str, sq: int) -> QPixmap | None:
        key = f"{condition}/{size}/{sq}"
        if key not in self._pix_cache:
            base = _CONDITION_FILE.get(condition)
            if base is None:
                self._pix_cache[key] = None
            else:
                # Try requested size first; fall back to Default when Mini isn't exported
                sizes = [size, "Default"] if size != "Default" else ["Default"]
                found = None
                for try_size in sizes:
                    for ext in (".png", ".svg"):
                        path = self._assets / "weather" / f"{base}_{try_size}{ext}"
                        if path.exists():
                            pix = QPixmap(str(path))
                            if not pix.isNull():
                                found = pix.scaled(
                                    sq, sq,
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation,
                                )
                                break
                    if found:
                        break
                self._pix_cache[key] = found
        return self._pix_cache[key]

    def _draw_icon(self, p: QPainter, rect: QRectF, condition: str, size: str):
        sq  = int(min(rect.width(), rect.height()))
        pix = self._get_pixmap(condition, size, sq)
        if pix is not None:
            p.drawPixmap(
                int(rect.x() + (rect.width()  - pix.width())  / 2),
                int(rect.y() + (rect.height() - pix.height()) / 2),
                pix,
            )
        else:
            label = _CONDITION_FALLBACK.get(condition, "?")
            font = QFont("Sans Serif")
            font.setPixelSize(max(9, int(sq * 0.75)))
            p.setFont(font)
            p.setPen(QColor("#888888"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    # ── main paint ────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        W, H    = self.width(), self.height()
        icon_w  = self._ICON_W
        right_x = icon_w
        right_w = W - icon_w
        strip_h = self._STRIP_H
        attr_h  = H - strip_h

        # ── Condition icon (left column, square centred) ─────────────────────
        sq = min(icon_w, H) - 20
        self._draw_icon(
            p,
            QRectF((icon_w - sq) / 2, (H - sq) / 2, sq, sq),
            self._condition, "Default",
        )

        # ── Attribute block (right top) ──────────────────────────────────────
        self._draw_attribute(p, right_x, 0, right_w, attr_h)

        # ── Forecast strip (right bottom) ────────────────────────────────────
        self._draw_forecast(p, right_x, H - strip_h, right_w, strip_h)

        p.end()

    # ── attribute block ───────────────────────────────────────────────────────

    def _load_attr_pixmap(self, icon_file: str, w: int, h: int) -> QPixmap | None:
        key = f"attr/{icon_file}/{w}x{h}"
        if key not in self._pix_cache:
            path = self._assets / "weather" / icon_file
            if path.exists():
                pix = QPixmap(str(path))
                self._pix_cache[key] = (
                    pix.scaled(w, h,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                    if not pix.isNull() else None
                )
            else:
                self._pix_cache[key] = None
        return self._pix_cache[key]

    def _draw_attribute(self, p: QPainter, x, y, w, h):
        attr_key, unit, icon_file = _METRICS[self._metric_idx]
        raw = self._attrs.get(attr_key)
        if raw is None:
            return

        value = float(raw)
        v = int(round(value))
        # Pressure values (hPa ~1013, Pa ~101325) get compressed to 2 digits
        if attr_key == "pressure":
            while abs(v) > 99:
                v //= 10
        num_str = f"{v}{unit}"

        icon_w_ = 90
        icon_h_ = 120
        pad_r   = 18
        gap     = 20

        icon_x = x + w - icon_w_ - pad_r
        icon_y = y + (h - icon_h_) / 2

        font = QFont("Sans Serif", 1, QFont.Weight.Bold)
        font.setPointSize(64)
        p.setFont(font)
        fm  = QFontMetricsF(font)
        tw  = fm.horizontalAdvance(num_str)
        num_right = icon_x - gap
        num_x     = num_right - tw
        num_y     = y + (h - fm.height()) / 2

        p.setPen(QColor("#2f2f2f"))
        p.drawText(QPointF(num_x, num_y + fm.ascent()), num_str)

        pix = self._load_attr_pixmap(icon_file, icon_w_, icon_h_)
        if pix is not None:
            p.drawPixmap(
                int(icon_x + (icon_w_ - pix.width())  / 2),
                int(icon_y + (icon_h_ - pix.height()) / 2),
                pix,
            )

    # ── forecast strip ────────────────────────────────────────────────────────

    def _draw_forecast(self, p: QPainter, x, y, w, h):
        slots = self._forecast
        if not slots:
            return

        strip_w = min(self._STRIP_W, w - 16)
        bg_x    = x + (w - strip_w) / 2
        pad_y   = 8
        bg_rect = QRectF(bg_x, y + pad_y, strip_w, h - pad_y * 2)

        row_h  = bg_rect.height() / 3
        slot_w = float(self._SLOT_W)

        font = QFont("Inter", 1, QFont.Weight.Bold)
        font.setPointSize(15)

        p.save()
        p.setClipRect(bg_rect)

        for i, slot in enumerate(slots):
            sx = bg_rect.x() + i * slot_w - self._scroll_x
            if sx + slot_w < bg_rect.x() or sx > bg_rect.right():
                continue
            sy = bg_rect.y()
            sw = slot_w

            # Fade to transparent over 30 px at each edge
            center_in_strip = sx + sw / 2 - bg_rect.x()
            if center_in_strip < _FADE_W:
                opacity = max(0.0, center_in_strip / _FADE_W)
            elif center_in_strip > strip_w - _FADE_W:
                opacity = max(0.0, (strip_w - center_in_strip) / _FADE_W)
            else:
                opacity = 1.0
            p.setOpacity(opacity)

            try:
                dt       = datetime.fromisoformat(slot.get("datetime", ""))
                hour_lbl = f"{dt.hour:02d}"
            except (ValueError, TypeError):
                hour_lbl = "--"

            cond   = slot.get("condition", "")
            temp   = slot.get("temperature")
            temp_s = f"{int(round(temp))}°" if temp is not None else ""

            # Row 1 — hour label
            p.setFont(font)
            p.setPen(QColor("#2f2f2f"))
            p.drawText(QRectF(sx, sy, sw, row_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       hour_lbl)

            # Row 2 — mini condition icon
            ico = 18
            self._draw_icon(p,
                            QRectF(sx + (sw - ico) / 2,
                                   sy + row_h + (row_h - ico) / 2,
                                   ico, ico),
                            cond, "Mini")

            # Row 3 — temperature
            p.setFont(font)
            p.setPen(QColor("#2f2f2f"))
            p.drawText(QRectF(sx, sy + 2 * row_h, sw, row_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       temp_s)

        p.setOpacity(1.0)
        p.restore()
