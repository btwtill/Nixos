"""Horizontal image-based slider (used for the music seek/volume bar).

Backdrop and fill images are stretched to the widget's full width; the fill
is cropped from the left up to the current value (not squashed), so partial
fills keep the same proportions as the source artwork.
"""
from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget, QSizePolicy


class LinearSlider(QWidget):
    """Interactive horizontal slider built entirely from images.

    bg_image     : backdrop, stretched to the widget's full width/track height
    fill_image   : "100%" fill artwork — only the left value-fraction slice
                   is drawn, scaled identically to how the backdrop stretches
    handle_image : drag handle, centred on the track at the current value
    """

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        bg_image: str = "",
        fill_image: str = "",
        handle_image: str = "",
        track_height: float = 20.0,
        handle_size: tuple = (19, 39),
        parent=None,
    ):
        super().__init__(parent)
        self._bg_pix     = QPixmap(bg_image)     if bg_image     else QPixmap()
        self._fill_pix   = QPixmap(fill_image)   if fill_image   else QPixmap()
        self._handle_pix = QPixmap(handle_image) if handle_image else QPixmap()
        self._track_h    = float(track_height)
        self._hw, self._hh = handle_size
        self._value = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(max(self._hh, int(self._track_h)))
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

    def set_value_silent(self, v: float):
        """Update position without emitting value_changed (e.g. playback sync)."""
        v = max(0.0, min(1.0, float(v)))
        if v != self._value:
            self._value = v
            self.update()

    # ── geometry ──────────────────────────────────────────────────────────────

    def _usable_width(self) -> float:
        return max(0.0, self.width() - self._hw)

    def _handle_cx(self) -> float:
        return self._hw / 2 + self._value * self._usable_width()

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        full_w  = float(self.width())
        track_y = (self.height() - self._track_h) / 2

        if not self._bg_pix.isNull():
            p.drawPixmap(
                QRectF(0, track_y, full_w, self._track_h),
                self._bg_pix,
                QRectF(self._bg_pix.rect()),
            )

        fill_w = self._handle_cx()
        if not self._fill_pix.isNull() and fill_w > 0 and full_w > 0:
            iw, ih  = self._fill_pix.width(), self._fill_pix.height()
            crop_w  = iw * (fill_w / full_w)
            p.drawPixmap(
                QRectF(0, track_y, fill_w, self._track_h),
                self._fill_pix,
                QRectF(0, 0, crop_w, ih),
            )

        if not self._handle_pix.isNull():
            pix = self._handle_pix.scaled(
                self._hw, self._hh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                int(self._handle_cx() - self._hw / 2),
                int(self.height() / 2 - self._hh / 2),
                pix,
            )

        p.end()

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._set_from_x(ev.position().x())

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton:
            self._set_from_x(ev.position().x())

    def _set_from_x(self, x: float):
        usable = self._usable_width()
        if usable <= 0:
            self.value = 0.0
            return
        self.value = (x - self._hw / 2) / usable
