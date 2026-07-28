"""Weather dashboard widget — top-left quadrant (521×245 px).

Layout
------
  [216×216 condition icon] | [large number + attribute icon   ]
                           | [      250×90 forecast strip     ]

The attribute block cycles through temperature / humidity / wind / pressure
on a timer (8 s) or when the user clicks anywhere in the right column.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter, QPainterPath, QPen, QBrush,
    QColor, QFont, QFontMetricsF, QLinearGradient, QPixmap,
)
from PyQt6.QtWidgets import QWidget

# ── condition → SVG base name ─────────────────────────────────────────────────

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

_CONDITION_EMOJI = {
    "clear-night": ")", "cloudy": "C", "exceptional": "!",
    "fog": "~",         "hail": "*",   "lightning": "Z",
    "lightning-rainy": "Z", "partlycloudy": "c", "pouring": ":",
    "rainy": ".",       "snowy": "*",  "snowy-rainy": "*",
    "sunny": "O",       "windy": "-",  "windy-variant": "-",
}

# (attr key, unit string, display name)
_METRICS = [
    ("temperature", "°",      "temperature"),
    ("humidity",    "%",      "humidity"),
    ("wind_speed",  " km/h",  "wind"),
    ("pressure",    " hPa",   "pressure"),
]

_STRIP_BG = QColor(25, 25, 25, 210)
_FADE_W   = 26


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red()   + t * (b.red()   - a.red())),
        int(a.green() + t * (b.green() - a.green())),
        int(a.blue()  + t * (b.blue()  - a.blue())),
    )


class WeatherWidget(QWidget):
    """Condition icon + cycling attribute display + hourly forecast strip."""

    _ICON_W   = 216
    _STRIP_H  = 90
    _STRIP_W  = 250
    _N_SLOTS  = 8
    _CYCLE_MS = 8_000

    def __init__(self, assets: Path, parent=None):
        super().__init__(parent)
        self._assets      = assets
        self._condition   = ""
        self._attrs: dict = {}
        self._forecast: list = []
        self._metric_idx  = 0
        self._pix_cache: dict[str, QPixmap | None] = {}

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
        self.update()

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and ev.position().x() > self._ICON_W:
            self._advance_metric()
            self._cycle_timer.start()  # reset auto-cycle on manual tap

    def _advance_metric(self):
        self._metric_idx = (self._metric_idx + 1) % len(_METRICS)
        self.update()

    # ── SVG / pixmap helpers ─────────────────────────────────────────────────

    def _get_pixmap(self, condition: str, size: str, sq: int) -> QPixmap | None:
        key = f"{condition}/{size}/{sq}"
        if key not in self._pix_cache:
            base = _CONDITION_FILE.get(condition)
            if base is None:
                self._pix_cache[key] = None
            else:
                # Nix build pre-converts SVGs → PNGs; fall back to SVG for dev runs
                for ext in (".png", ".svg"):
                    path = self._assets / "weather" / f"{base}_{size}{ext}"
                    if path.exists():
                        pix = QPixmap(str(path))
                        if not pix.isNull():
                            self._pix_cache[key] = pix.scaled(
                                sq, sq,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            break
                else:
                    self._pix_cache[key] = None
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
            # Text fallback: show the condition name so it's legible during dev
            label = condition.replace("-", "\n") if condition else "?"
            font = QFont("Sans Serif")
            font.setPixelSize(max(11, int(sq * 0.10)))
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
        sq  = min(icon_w, H) - 20
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

    def _draw_attribute(self, p: QPainter, x, y, w, h):
        attr_key, unit, _ = _METRICS[self._metric_idx]
        raw = self._attrs.get(attr_key)
        if raw is None:
            return

        value    = float(raw)
        num_str  = f"{int(round(value))}{unit}"
        icon_w_  = 50
        icon_h_  = 78
        gap      = 14

        font = QFont("Sans Serif", 1, QFont.Weight.Bold)
        font.setPixelSize(58)
        p.setFont(font)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(num_str)

        total_w = tw + gap + icon_w_
        tx = x + (w - total_w) / 2
        ty = y + (h - fm.height()) / 2

        p.setPen(QColor("#FFFFFF"))
        p.drawText(QPointF(tx, ty + fm.ascent()), num_str)

        self._draw_metric_icon(
            p,
            QRectF(tx + tw + gap, y + (h - icon_h_) / 2, icon_w_, icon_h_),
            attr_key,
            value,
        )

    def _draw_metric_icon(self, p: QPainter, rect: QRectF, metric: str, value: float):
        if metric == "temperature":
            self._draw_thermometer(p, rect, value)
        elif metric == "humidity":
            self._draw_droplet(p, rect, value)
        elif metric == "wind_speed":
            self._draw_wind_lines(p, rect)
        else:
            self._draw_circle_gauge(p, rect)

    def _draw_thermometer(self, p: QPainter, rect: QRectF, temp_c: float):
        cx      = rect.center().x()
        tube_w  = rect.width() * 0.30
        bulb_r  = rect.width() * 0.44
        tube_bot = rect.bottom() - bulb_r * 1.25
        tube_top = rect.top()

        cold = QColor("#3860FF")
        hot  = QColor("#FF3010")
        frac = max(0.0, min(1.0, (temp_c + 10) / 50))
        fill = _lerp_color(cold, hot, frac)

        p.setPen(Qt.PenStyle.NoPen)
        # tube background
        tube_rect = QRectF(cx - tube_w/2, tube_top, tube_w, tube_bot - tube_top)
        p.setBrush(QColor(55, 55, 55))
        p.drawRoundedRect(tube_rect, tube_w/2, tube_w/2)
        # tube fill
        fill_h = (tube_bot - tube_top) * frac
        if fill_h > 0:
            p.setBrush(fill)
            p.drawRoundedRect(
                QRectF(cx - tube_w/2, tube_bot - fill_h, tube_w, fill_h + tube_w/2),
                tube_w/2, tube_w/2,
            )
        # bulb shadow
        bulb_cy = tube_bot + bulb_r * 0.52
        p.setBrush(QColor(55, 55, 55))
        p.drawEllipse(QPointF(cx, bulb_cy), bulb_r, bulb_r)
        # bulb fill
        p.setBrush(fill)
        p.drawEllipse(QPointF(cx, bulb_cy), bulb_r * 0.80, bulb_r * 0.80)

    def _draw_droplet(self, p: QPainter, rect: QRectF, humidity_pct: float):
        cx  = rect.center().x()
        top = rect.top()
        r   = rect.width() * 0.42
        bot = rect.bottom()

        path = QPainterPath()
        path.moveTo(cx, top)
        path.cubicTo(cx + r * 1.1, top + (bot - top) * 0.55,
                     cx + r,       bot,
                     cx,           bot)
        path.cubicTo(cx - r,       bot,
                     cx - r * 1.1, top + (bot - top) * 0.55,
                     cx,           top)

        frac  = max(0.0, min(1.0, humidity_pct / 100))
        alpha = 80 + int(frac * 175)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(40, 110, 230, alpha))
        p.drawPath(path)

    def _draw_wind_lines(self, p: QPainter, rect: QRectF):
        pen = QPen(QColor(160, 160, 210), 2.2,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        h_step = rect.height() / 3
        lengths = [1.0, 0.72, 0.50]
        for i, frac in enumerate(lengths):
            cy  = rect.top() + (i + 0.5) * h_step
            lw  = rect.width() * frac
            lx0 = rect.left()
            lx1 = lx0 + lw
            ctrl_y = cy - h_step * 0.18
            path = QPainterPath()
            path.moveTo(lx0, cy)
            path.quadTo((lx0 + lx1) / 2, ctrl_y, lx1, cy)
            p.drawPath(path)

    def _draw_circle_gauge(self, p: QPainter, rect: QRectF):
        p.setPen(QPen(QColor(90, 90, 90), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect.adjusted(4, 4, -4, -4))

    # ── forecast strip ────────────────────────────────────────────────────────

    def _draw_forecast(self, p: QPainter, x, y, w, h):
        slots = self._forecast[:self._N_SLOTS]
        if not slots:
            return

        strip_w  = min(self._STRIP_W, w - 16)
        bg_x     = x + (w - strip_w) / 2
        pad_y    = 8
        bg_rect  = QRectF(bg_x, y + pad_y, strip_w, h - pad_y * 2)
        radius   = 13.0

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_STRIP_BG)
        p.drawRoundedRect(bg_rect, radius, radius)

        slot_w = bg_rect.width() / len(slots)
        row_h  = bg_rect.height() / 3

        # Clip so content is contained inside the pill
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(bg_rect, radius, radius)
        p.setClipPath(clip)

        for i, slot in enumerate(slots):
            sx = bg_rect.x() + i * slot_w
            sy = bg_rect.y()
            sw = slot_w

            try:
                dt      = datetime.fromisoformat(slot.get("datetime", ""))
                hour_lbl = f"{dt.hour}"
            except (ValueError, TypeError):
                hour_lbl = "--"

            cond   = slot.get("condition", "")
            temp   = slot.get("temperature")
            temp_s = f"{int(round(temp))}°" if temp is not None else ""

            # Row 1 — hour label
            f1 = QFont("Sans Serif")
            f1.setPixelSize(11)
            p.setFont(f1)
            p.setPen(QColor(145, 145, 145))
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
            f3 = QFont("Sans Serif")
            f3.setPixelSize(11)
            p.setFont(f3)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(sx, sy + 2 * row_h, sw, row_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       temp_s)

        # Left and right edge fade overlay
        fade_w = float(_FADE_W)
        bg_color = _STRIP_BG
        fade_color = QColor(bg_color.red(), bg_color.green(), bg_color.blue(), 0)

        for left in (True, False):
            if left:
                grad = QLinearGradient(bg_rect.left(), 0, bg_rect.left() + fade_w, 0)
                grad.setColorAt(0.0, bg_color)
                grad.setColorAt(1.0, fade_color)
                fade_rect = QRectF(bg_rect.left(), bg_rect.top(), fade_w, bg_rect.height())
            else:
                grad = QLinearGradient(bg_rect.right() - fade_w, 0, bg_rect.right(), 0)
                grad.setColorAt(0.0, fade_color)
                grad.setColorAt(1.0, bg_color)
                fade_rect = QRectF(bg_rect.right() - fade_w, bg_rect.top(), fade_w, bg_rect.height())

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(fade_rect)

        p.restore()
