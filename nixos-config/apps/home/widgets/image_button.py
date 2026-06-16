from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap, QColor, QFont
from PyQt6.QtWidgets import QAbstractButton


class ImageButton(QAbstractButton):
    """Button with a separate image for default and active (pressed / checked) state.

    Falls back to a coloured circle + text label when images are not available.

    Parameters
    ----------
    default_image : path to the idle-state image (None = fallback)
    active_image  : path to the pressed / on-state image (None = fallback)
    size          : fixed (w, h) in pixels
    checkable     : True → toggle (lights), False → momentary (transport)
    label         : text shown in the fallback circle
    """

    def __init__(
        self,
        default_image: str | None = None,
        active_image:  str | None = None,
        size: tuple[int, int] = (40, 40),
        checkable: bool = False,
        label: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._default_pix = QPixmap(default_image) if default_image else QPixmap()
        self._active_pix  = QPixmap(active_image)  if active_image  else QPixmap()
        self._label = label
        self.setFixedSize(*size)
        self.setCheckable(checkable)

    # ── internal ──────────────────────────────────────────────────────────────

    def _is_active(self) -> bool:
        return self.isChecked() or self.isDown()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )

        pix = self._active_pix if self._is_active() else self._default_pix
        if not pix.isNull():
            scaled = pix.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                (self.width()  - scaled.width())  // 2,
                (self.height() - scaled.height()) // 2,
                scaled,
            )
        else:
            # Fallback rendering
            active = self._is_active()
            circle_color = QColor("#FFEE55") if active else QColor("#383838")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(circle_color)
            m = 3
            p.drawEllipse(m, m, self.width() - 2 * m, self.height() - 2 * m)
            if self._label:
                p.setPen(QColor("#111111") if active else QColor("#888888"))
                p.setFont(QFont("monospace", max(10, self.height() // 4),
                                QFont.Weight.Bold))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()
