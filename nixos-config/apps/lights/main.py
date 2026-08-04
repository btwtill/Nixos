import sys
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont,
    QRadialGradient, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

W, H     = 814, 490
PAGER_H  = 40
CONTENT_H = H - PAGER_H   # 450

# ── Page 1 layout constants ────────────────────────────────────────────────────
FLOORPLAN_W = 750
FLOORPLAN_H = 352
FLOORPLAN_X = (W - FLOORPLAN_W) // 2     # 32
FLOORPLAN_Y = 8

PRESETS_W = 689
PRESETS_H = 73
PRESETS_X = (W - PRESETS_W) // 2         # 62
PRESETS_Y = FLOORPLAN_Y + FLOORPLAN_H + 5  # 365

# ── Page 2 scene definitions: (name, [rgb, rgb, rgb]) ─────────────────────────
_SCENES = [
    ("Cozy Evening",  [(255, 130, 50),  (255,  90, 20),  (180,  50, 10)]),
    ("Focus",         [(160, 200, 255), (180, 215, 255), (140, 185, 255)]),
    ("Party",         [(170,  0, 255),  (255,  0, 140),  (0,  210, 255)]),
    ("Relax",         [(50,  90, 200),  (110,  70, 200), (60, 170, 150)]),
    ("Movie Night",   [(170,  15, 15),  (110,  35,  5),  (70,   5,  35)]),
    ("Morning",       [(255, 215,  90), (255, 170,  70), (235, 235, 190)]),
]

# ── Page 2 button grid ─────────────────────────────────────────────────────────
_BM  = 16   # margin
_GX  = 12   # horizontal gap
_GY  = 12   # vertical gap
_COLS = 2
_ROWS = 3
_BW  = (W - _BM * 2 - _GX * (_COLS - 1)) // _COLS          # 385
_BH  = (CONTENT_H - _BM * 2 - _GY * (_ROWS - 1)) // _ROWS  # 131
_BR  = 22.0  # corner radius


def _scene_button_pixmap(w: int, h: int, name: str, colors: list) -> QPixmap:
    """Render one scene button into an off-screen pixmap."""
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    rect  = QRectF(0.75, 0.75, w - 1.5, h - 1.5)
    path  = QPainterPath()
    path.addRoundedRect(rect, _BR, _BR)

    # Dark base
    p.setClipPath(path)
    p.fillPath(path, QColor(10, 10, 16))

    # Radial gradient blobs — Screen mode = additive light mixing
    positions  = [(0.35, 0.40), (0.72, 0.30), (0.50, 0.73)]
    blob_r     = min(w, h) * 0.68

    for (fx, fy), rgb in zip(positions, colors):
        cx   = w * fx
        cy   = h * fy
        grad = QRadialGradient(cx, cy, blob_r)
        c    = QColor(*rgb)
        grad.setColorAt(0.0, c)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.fillRect(QRectF(0, 0, w, h), grad)

    # Glassy border
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setClipping(False)
    pen = QPen(QColor(255, 255, 255, 45))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    # Label
    font = QFont("Inter", 13, QFont.Weight.Medium)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 225))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, name)

    p.end()
    return pix


class LightsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._page           = 0
        self._drag_start_x: float | None = None
        self._scene_pixmaps: list[QPixmap] = []
        self._build_scene_pixmaps()

    def _build_scene_pixmaps(self):
        self._scene_pixmaps = [
            _scene_button_pixmap(_BW, _BH, name, colors)
            for name, colors in _SCENES
        ]

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start_x = ev.position().x()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_start_x is not None:
            delta = ev.position().x() - self._drag_start_x
            if abs(delta) > 60:
                new = self._page + (-1 if delta < 0 else 1)
                if 0 <= new <= 1:
                    self._page = new
                    self.update()
            self._drag_start_x = None

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if self._page == 0:
            self._draw_page1(p)
        else:
            self._draw_page2(p)

        self._draw_pager(p)
        p.end()

    def _draw_page1(self, p: QPainter):
        font_label = QFont("Inter", 12)

        # Floorplan placeholder
        fp = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)
        p.fillRect(fp, QColor(55, 80, 130, 160))
        p.setPen(QColor(160, 190, 255, 200))
        p.setFont(font_label)
        p.drawText(fp, Qt.AlignmentFlag.AlignCenter, f"Floorplan  {FLOORPLAN_W}×{FLOORPLAN_H}")

        # Presets row placeholder
        pr = QRectF(PRESETS_X, PRESETS_Y, PRESETS_W, PRESETS_H)
        p.fillRect(pr, QColor(70, 130, 80, 160))
        p.setPen(QColor(170, 255, 180, 200))
        p.drawText(pr, Qt.AlignmentFlag.AlignCenter, f"Presets row  {PRESETS_W}×{PRESETS_H}")

        # Remaining gap
        gap_y = PRESETS_Y + PRESETS_H
        gap_h = CONTENT_H - gap_y
        if gap_h > 0:
            gap_r = QRectF(0, gap_y, W, gap_h)
            p.fillRect(gap_r, QColor(80, 80, 80, 50))
            p.setPen(QColor(140, 140, 140, 100))
            font_sm = QFont("Inter", 10)
            p.setFont(font_sm)
            p.drawText(gap_r, Qt.AlignmentFlag.AlignCenter, f"remaining  {W}×{int(gap_h)}")

    def _draw_page2(self, p: QPainter):
        for idx, pix in enumerate(self._scene_pixmaps):
            col = idx % _COLS
            row = idx // _COLS
            bx  = _BM + col * (_BW + _GX)
            by  = _BM + row * (_BH + _GY)
            p.drawPixmap(bx, by, pix)

    def _draw_pager(self, p: QPainter):
        dot_r   = 4.0
        dot_gap = 14.0
        n       = 2
        total_w = n * dot_r * 2 + (n - 1) * dot_gap
        sx      = (W - total_w) / 2
        cy      = CONTENT_H + PAGER_H / 2

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            cx = sx + i * (dot_r * 2 + dot_gap) + dot_r
            p.setBrush(QColor(255, 255, 255, 220 if i == self._page else 70))
            p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)


class LightsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lights")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(LightsWidget())
        self.setFixedSize(W, H)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lights")
    window = LightsApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
