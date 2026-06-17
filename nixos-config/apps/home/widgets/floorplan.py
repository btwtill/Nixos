from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from .image_button import ImageButton


class FloorplanWidget(QWidget):
    """Floorplan background image with toggleable light buttons overlaid.

    Each light button is positioned so its centre sits at the (x, y) coordinate
    specified in LightConfig.position, which is in widget-pixel space (i.e. the
    coordinate space of floorplan_bg.png when it fills the 521×245 widget).
    """

    light_toggled = pyqtSignal(str, bool)   # (light_name, is_on)

    def __init__(self, lights: list, assets: Path, parent=None):
        super().__init__(parent)
        bg_path = assets / "floorplan" / "Floorplan_dark_small.png"
        self._bg = QPixmap(str(bg_path))
        self._buttons: dict[str, ImageButton] = {}

        for lc in lights:
            btn = ImageButton(
                default_image=str(assets / lc.icon_default),
                active_image =str(assets / lc.icon_on),
                size=lc.icon_size,
                checkable=True,
                label="●",
                parent=self,
            )
            bx, by = lc.position
            w, h   = lc.icon_size
            btn.move(bx - w // 2, by - h // 2)
            btn.setToolTip(lc.name)
            name = lc.name
            btn.toggled.connect(
                lambda checked, n=name: self.light_toggled.emit(n, checked)
            )
            self._buttons[lc.name] = btn

    # ── public ────────────────────────────────────────────────────────────────

    def set_light(self, name: str, on: bool):
        """Programmatically update a light's visual state."""
        if name in self._buttons:
            btn = self._buttons[name]
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        if not self._bg.isNull():
            p.drawPixmap(
                0, 0,
                self._bg.scaled(
                    self.width(), self.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        else:
            # Fallback: dark rectangle with a subtle grid to suggest a floorplan
            p.fillRect(self.rect(), Qt.GlobalColor.black)
            p.setPen(Qt.GlobalColor.darkGray)
            step = 40
            for x in range(0, self.width(), step):
                p.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), step):
                p.drawLine(0, y, self.width(), y)
        p.end()
