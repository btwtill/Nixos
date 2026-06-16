"""Circular arc slider widget.

Angle convention used throughout this file
------------------------------------------
0° = 12 o'clock (top), positive angles go *clockwise* on screen.
Conversion to Qt's drawArc system (0° = 3 o'clock, positive = CCW):
    qt_angle = 90 - screen_angle
    clockwise arc → negative span in Qt
"""
from __future__ import annotations
import math
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap
from PyQt6.QtWidgets import QWidget


# ── colour helpers ────────────────────────────────────────────────────────────

def _lerp_color(c0: QColor, c1: QColor, t: float) -> QColor:
    return QColor(
        int(c0.red()   + t * (c1.red()   - c0.red())),
        int(c0.green() + t * (c1.green() - c0.green())),
        int(c0.blue()  + t * (c1.blue()  - c0.blue())),
    )


def _sample_stops(stops: list[tuple[float, QColor]], t: float) -> QColor:
    """Linear-interpolate across a list of (position, QColor) stops."""
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return _lerp_color(c0, c1, f)
    return stops[-1][1] if stops else QColor("#FFFFFF")


# ── widget ────────────────────────────────────────────────────────────────────

class ArcSlider(QWidget):
    """Interactive circular arc slider.

    The arc sweeps clockwise from *start_angle* to *end_angle*.
    Dragging the handle emits value_changed(float) with a value in [0, 1].
    """

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        center: tuple,
        radius: float,
        start_angle: float,
        end_angle: float,
        track_width: float = 10.0,
        track_color: str = "#252525",
        fill_color=None,        # str for solid, list of (stop, hex) for gradient
        bg_image: str = "",
        handle_image: str = "",
        handle_size: tuple = (26, 26),
        parent=None,
    ):
        super().__init__(parent)
        self._cx, self._cy = float(center[0]), float(center[1])
        self._radius  = float(radius)
        self._start   = float(start_angle)
        self._end     = float(end_angle)
        self._tw      = float(track_width)
        self._tc      = QColor(track_color)
        self._value   = 0.0
        self._hw, self._hh = handle_size

        if fill_color is None or isinstance(fill_color, str):
            self._fill_solid = QColor(fill_color or "#888888")
            self._fill_grad: list | None = None
        else:
            self._fill_solid = None
            self._fill_grad  = [(pos, QColor(col)) for pos, col in fill_color]

        self._bg_pix     = QPixmap(bg_image)     if bg_image     else QPixmap()
        self._handle_pix = QPixmap(handle_image) if handle_image else QPixmap()

        self.setMouseTracking(True)

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if v != self._value:
            self._value = v
            self.update()
            self.value_changed.emit(v)

    # ── geometry ──────────────────────────────────────────────────────────────

    def _span(self) -> float:
        """Clockwise arc span in degrees, always in (0, 360]."""
        return (self._end - self._start) % 360 or 360.0

    def _angle_at(self, t: float) -> float:
        """Screen angle (0=top, CW+) for slider value t in [0, 1]."""
        return self._start + t * self._span()

    def _to_point(self, screen_angle: float) -> QPointF:
        r = math.radians(screen_angle)
        return QPointF(
            self._cx + self._radius * math.sin(r),
            self._cy - self._radius * math.cos(r),
        )

    @staticmethod
    def _to_qt(screen_angle: float) -> float:
        """Screen → Qt angle (0=right, CCW+, in degrees)."""
        return 90.0 - screen_angle

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background image — centred, aspect-ratio preserved
        if not self._bg_pix.isNull():
            scaled = self._bg_pix.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                (self.width()  - scaled.width())  // 2,
                (self.height() - scaled.height()) // 2,
                scaled,
            )

        span     = self._span()
        qt_start = self._to_qt(self._start)
        rect     = QRectF(
            self._cx - self._radius, self._cy - self._radius,
            self._radius * 2, self._radius * 2,
        )

        # Full-range track (dark background arc)
        p.setPen(QPen(self._tc, self._tw,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(round(qt_start * 16)), int(round(-span * 16)))

        # Fill arc (0 → current value)
        if self._value > 0.0:
            if self._fill_solid is not None:
                self._draw_solid_fill(p, rect, span, qt_start)
            else:
                self._draw_gradient_fill(p, rect, span, qt_start)

        # Handle
        hp = self._to_point(self._angle_at(self._value))
        if not self._handle_pix.isNull():
            pix = self._handle_pix.scaled(
                self._hw, self._hh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                int(hp.x() - self._hw / 2),
                int(hp.y() - self._hh / 2),
                pix,
            )
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#DDDDDD"))
            p.drawEllipse(hp, 10.0, 10.0)

        p.end()

    def _draw_solid_fill(self, painter: QPainter, rect: QRectF,
                         span: float, qt_start: float):
        painter.setPen(QPen(self._fill_solid, self._tw,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(
            rect,
            int(round(qt_start * 16)),
            int(round(-span * self._value * 16)),
        )

    def _draw_gradient_fill(self, painter: QPainter, rect: QRectF,
                            span: float, qt_start: float):
        """Draw the fill as 90 short arcs, each sampled from the gradient.

        The gradient maps absolute positions along the arc (0 = start_angle,
        1 = end_angle), so the revealed colour depends on arc position rather
        than on how far the user has dragged.
        """
        n = 90
        for i in range(n):
            t0 = i / n
            if t0 >= self._value:
                break
            t1    = min((i + 1) / n, self._value)
            color = _sample_stops(self._fill_grad, (t0 + t1) / 2)  # type: ignore[arg-type]

            is_first = (i == 0)
            is_last  = (t1 >= self._value)
            cap = (Qt.PenCapStyle.RoundCap
                   if (is_first or is_last) else Qt.PenCapStyle.FlatCap)

            painter.setPen(QPen(color, self._tw, Qt.PenStyle.SolidLine, cap))
            seg_start = qt_start - t0 * span          # decreasing → CW on screen
            seg_span  = -(t1 - t0) * span             # negative   → CW in Qt
            painter.drawArc(
                rect,
                int(round(seg_start * 16)),
                int(round(seg_span  * 16)),
            )

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._set_from_pos(ev.position())

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton:
            self._set_from_pos(ev.position())

    def _set_from_pos(self, pos: QPointF):
        dx = pos.x() - self._cx
        dy = pos.y() - self._cy
        # Screen angle (0=top, CW+), normalised to [0, 360)
        angle = math.degrees(math.atan2(dx, -dy)) % 360
        start = self._start % 360
        span  = self._span()
        rel   = (angle - start) % 360
        if rel <= span:
            self.value = rel / span
        else:
            # Outside arc — snap to nearest endpoint
            self.value = 1.0 if (rel - span) < (360 - span) / 2 else 0.0
