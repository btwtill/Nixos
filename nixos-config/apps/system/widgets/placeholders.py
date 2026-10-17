"""Placeholder graphics — plain QPainter shapes until the Figma designs land.

Each widget keeps a tiny public API (set_value / push / set_state) so the
drawing can be swapped for image assets later without touching the pages.
"""
from __future__ import annotations
from collections import deque

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

import config


def level_color(fraction: float) -> str:
    if fraction >= 0.9:
        return config.BAD
    if fraction >= 0.7:
        return config.WARN
    return config.ACCENT


class Bar(QWidget):
    """Horizontal fill bar, value in 0..1."""

    def __init__(self, height: int = 10, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._value = 0.0

    def set_value(self, fraction: float):
        self._value = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setBrush(QColor(config.CARD_ALT))
        p.drawRoundedRect(r, radius, radius)
        if self._value > 0:
            fill = QRectF(r.x(), r.y(), max(r.width() * self._value, r.height()), r.height())
            p.setBrush(QColor(level_color(self._value)))
            p.drawRoundedRect(fill, radius, radius)


class Sparkline(QWidget):
    """Line chart of the last N samples, values in 0..1."""

    def __init__(self, length: int = config.HISTORY_LEN, parent=None):
        super().__init__(parent)
        self._data: deque[float] = deque(maxlen=length)
        self.setMinimumHeight(30)

    def push(self, fraction: float):
        self._data.append(max(0.0, min(1.0, fraction)))
        self.update()

    def paintEvent(self, _):
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        step = w / (self._data.maxlen - 1)
        x0 = w - step * (len(self._data) - 1)
        pts = [QPointF(x0 + i * step, h - 2 - v * (h - 4)) for i, v in enumerate(self._data)]

        area = QPainterPath(QPointF(pts[0].x(), h))
        for pt in pts:
            area.lineTo(pt)
        area.lineTo(QPointF(pts[-1].x(), h))
        fill = QColor(config.ACCENT)
        fill.setAlpha(50)
        p.fillPath(area, fill)

        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        p.setPen(QPen(QColor(config.ACCENT), 2))
        p.drawPath(line)


class StatusDot(QWidget):
    """Coloured circle for a unit/app state."""

    COLORS = {
        "active":     config.OK,
        "running":    config.OK,
        "activating": config.WARN,
        "reloading":  config.WARN,
        "failed":     config.BAD,
    }

    def __init__(self, size: int = 14, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(config.TEXT_SEC)

    def set_state(self, state: str):
        self._color = QColor(self.COLORS.get(state, config.TEXT_SEC))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))


class Card(QFrame):
    """Rounded panel with a small caption — base for every stat tile."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ background: {config.CARD}; border-radius: 12px; }}"
            f"QLabel {{ background: transparent; color: {config.TEXT}; }}"
        )
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 10, 14, 10)
        self.body.setSpacing(4)
        caption = QLabel(title.upper())
        caption.setStyleSheet(f"color: {config.TEXT_SEC}; font-size: 11px; letter-spacing: 1px;")
        self.body.addWidget(caption)


class StatTile(Card):
    """Caption, big value, subtitle, plus optional bar and sparkline."""

    def __init__(self, title: str, bar: bool = True, sparkline: bool = False, parent=None):
        super().__init__(title, parent)
        self.value = QLabel("–")
        self.value.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color: {config.TEXT_SEC}; font-size: 12px;")
        self.body.addWidget(self.value)
        self.body.addWidget(self.sub)
        self.bar = Bar(8) if bar else None
        self.spark = Sparkline() if sparkline else None
        if self.spark:
            self.body.addWidget(self.spark, 1)
        else:
            self.body.addStretch(1)
        if self.bar:
            self.body.addWidget(self.bar)
