import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont,
    QRadialGradient, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

W, H      = 814, 490
PAGER_H   = 40
CONTENT_H = H - PAGER_H   # 450

ASSETS_DIR = Path(__file__).parent / "assets"

# ── Page 1 layout constants ────────────────────────────────────────────────────
FLOORPLAN_W = 750
FLOORPLAN_H = 353   # actual image height
FLOORPLAN_X = (W - FLOORPLAN_W) // 2       # 32
FLOORPLAN_Y = 8

PRESETS_W = 689
PRESETS_H = 73
PRESETS_X = (W - PRESETS_W) // 2           # 62
PRESETS_Y = FLOORPLAN_Y + FLOORPLAN_H + 5  # 366

# ── Page 2 scene definitions: (name, [rgb, rgb, rgb]) ─────────────────────────
_SCENES = [
    ("Cozy Evening",  [(255, 130, 50),  (255,  90, 20),  (180,  50, 10)]),
    ("Focus",         [(160, 200, 255), (180, 215, 255), (140, 185, 255)]),
    ("Party",         [(170,  0, 255),  (255,  0, 140),  (0,  210, 255)]),
    ("Relax",         [(50,  90, 200),  (110,  70, 200), (60, 170, 150)]),
    ("Movie Night",   [(170,  15, 15),  (110,  35,  5),  (70,   5,  35)]),
    ("Morning",       [(255, 215,  90), (255, 170,  70), (235, 235, 190)]),
]

# ── Page 2 button grid — 3 columns × 2 rows of square buttons ─────────────────
_COLS = 3
_ROWS = 2
_GX   = 12
_GY   = 12
_SQ   = min(
    (W         - _GX * (_COLS - 1)) // _COLS,   # width-limited
    (CONTENT_H - _GY * (_ROWS - 1)) // _ROWS,   # height-limited
)  # 203
_BM_X = (W         - _COLS * _SQ - _GX * (_COLS - 1)) // 2  # horizontal centering
_BM_Y = (CONTENT_H - _ROWS * _SQ - _GY * (_ROWS - 1)) // 2  # vertical centering
_BR   = 24.0  # corner radius


def _scene_button_pixmap(size: int, name: str, colors: list) -> QPixmap:
    """Render one square scene button into an off-screen pixmap."""
    w = h = size
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    full_rect = QRectF(0, 0, w, h)
    path = QPainterPath()
    path.addRoundedRect(full_rect, _BR, _BR)

    # Dark base
    p.setClipPath(path)
    p.fillPath(path, QColor(10, 10, 16))

    # ── Blob positions for a square (triangular arrangement) ──────────────────
    primary_pos = [(0.28, 0.28), (0.72, 0.28), (0.50, 0.75)]

    # Primary blobs — large radius, reduced alpha for moderate brightness
    big_r = w * 0.82
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    for (fx, fy), rgb in zip(primary_pos, colors):
        grad = QRadialGradient(w * fx, h * fy, big_r)
        c = QColor(*rgb)
        grad.setColorAt(0.00, QColor(c.red(), c.green(), c.blue(), 140))
        grad.setColorAt(0.45, QColor(c.red(), c.green(), c.blue(),  90))
        grad.setColorAt(0.75, QColor(c.red(), c.green(), c.blue(),  25))
        grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(full_rect, grad)

    # Secondary midpoint blobs — averaged hue, dimmer
    mid_r = w * 0.48
    for (p0, p1), (c0, c1) in zip(
        [(primary_pos[0], primary_pos[1]),
         (primary_pos[1], primary_pos[2]),
         (primary_pos[0], primary_pos[2])],
        [(colors[0], colors[1]),
         (colors[1], colors[2]),
         (colors[0], colors[2])],
    ):
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        avg = ((c0[0] + c1[0]) // 2, (c0[1] + c1[1]) // 2, (c0[2] + c1[2]) // 2)
        grad = QRadialGradient(w * mx, h * my, mid_r)
        c = QColor(*avg)
        grad.setColorAt(0.00, QColor(c.red(), c.green(), c.blue(), 120))
        grad.setColorAt(0.60, QColor(c.red(), c.green(), c.blue(),  40))
        grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(full_rect, grad)

    # ── Inner rim glow — stacked strokes of decreasing width, same low alpha.
    # Each pixel near the edge is hit by more strokes than pixels further in,
    # producing a gradient that fades from the rim toward the center.
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for stroke_w in (18, 13, 9, 5, 2):
        pen = QPen(QColor(255, 255, 255, 20))
        pen.setWidthF(float(stroke_w))
        p.setPen(pen)
        p.drawPath(path)   # clip keeps only the inner half of each stroke

    # Label
    p.setClipping(False)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    font = QFont("Inter", 13, QFont.Weight.Medium)
    p.setFont(font)
    p.setPen(QColor(0x2f, 0x2f, 0x2f))
    p.drawText(full_rect, Qt.AlignmentFlag.AlignCenter, name)

    p.end()
    return pix


class LightsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._page           = 0
        self._drag_start_x: float | None = None

        self._floorplan_pix  = QPixmap(str(ASSETS_DIR / "floorplan.png"))
        self._pager_active   = QPixmap(str(ASSETS_DIR / "PagerPerlActive.png"))
        self._pager_inactive = QPixmap(str(ASSETS_DIR / "PagerPerlInactive.png"))

        self._scene_pixmaps: list[QPixmap] = [
            _scene_button_pixmap(_SQ, name, colors)
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
                # Swipe left (delta < 0) → next page; swipe right → previous
                new = self._page + (1 if delta < 0 else -1)
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
        # Floorplan image
        if not self._floorplan_pix.isNull():
            p.drawPixmap(FLOORPLAN_X, FLOORPLAN_Y, self._floorplan_pix)
        else:
            fp = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)
            p.fillRect(fp, QColor(55, 80, 130, 160))
            p.setPen(QColor(160, 190, 255, 200))
            p.setFont(QFont("Inter", 12))
            p.drawText(fp, Qt.AlignmentFlag.AlignCenter, "floorplan.png not found")

        # Presets row placeholder
        pr = QRectF(PRESETS_X, PRESETS_Y, PRESETS_W, PRESETS_H)
        p.fillRect(pr, QColor(70, 130, 80, 160))
        p.setPen(QColor(170, 255, 180, 200))
        p.setFont(QFont("Inter", 12))
        p.drawText(pr, Qt.AlignmentFlag.AlignCenter, f"Presets row  {PRESETS_W}×{PRESETS_H}")

        # Remaining gap
        gap_y = PRESETS_Y + PRESETS_H
        gap_h = CONTENT_H - gap_y
        if gap_h > 0:
            p.fillRect(QRectF(0, gap_y, W, gap_h), QColor(80, 80, 80, 50))
            p.setPen(QColor(140, 140, 140, 100))
            p.setFont(QFont("Inter", 10))
            p.drawText(QRectF(0, gap_y, W, gap_h),
                       Qt.AlignmentFlag.AlignCenter,
                       f"remaining  {W}×{int(gap_h)}")

    def _draw_page2(self, p: QPainter):
        for idx, pix in enumerate(self._scene_pixmaps):
            col = idx % _COLS
            row = idx // _COLS
            bx  = _BM_X + col * (_SQ + _GX)
            by  = _BM_Y + row * (_SQ + _GY)
            p.drawPixmap(bx, by, pix)

    def _draw_pager(self, p: QPainter):
        n       = 2
        gap     = 12
        pw_a    = self._pager_active.width()   if not self._pager_active.isNull()   else 34
        pw_i    = self._pager_inactive.width() if not self._pager_inactive.isNull() else 34
        ph_a    = self._pager_active.height()  if not self._pager_active.isNull()   else 17
        ph_i    = self._pager_inactive.height()if not self._pager_inactive.isNull() else 16
        total_w = pw_a + gap + pw_i
        sx      = (W - total_w) // 2
        cy      = CONTENT_H + PAGER_H // 2

        for i in range(n):
            if i == self._page:
                pix = self._pager_active
                pw, ph = pw_a, ph_a
            else:
                pix = self._pager_inactive
                pw, ph = pw_i, ph_i
            x = sx + i * (pw_i + gap)
            y = cy - ph // 2
            if not pix.isNull():
                p.drawPixmap(x, y, pix)


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
