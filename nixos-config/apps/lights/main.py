from __future__ import annotations
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

# ── Page 1 layout ──────────────────────────────────────────────────────────────
FLOORPLAN_W = 750
FLOORPLAN_H = 353
FLOORPLAN_X = (W - FLOORPLAN_W) // 2
FLOORPLAN_Y = 8

PRESETS_W = 689
PRESETS_H = 73
PRESETS_X = (W - PRESETS_W) // 2
PRESETS_Y = FLOORPLAN_Y + FLOORPLAN_H + 5  # 366

_LIGHT_SZ = 40   # display size of each light icon on the floorplan (px)

# ── Preset row buttons ─────────────────────────────────────────────────────────
_BTN_PAD = 8
_BTN_GAP = 10
_BTN_H   = PRESETS_H - _BTN_PAD * 2   # 57

# (normal_asset, hi_asset_or_None, mode)
# mode: "normal" | "momentary" | "toggle"
_LEFT_DEFS = [
    ("SelectAllLights_Button.png",   None,                                      "normal"),
    ("AddNewLightsScene_Button.png", "AddNewLightsScene_Button_Highlighted.png","momentary"),
    ("LightSettings_Button.png",     "LightSettings_Button_Highlighted.png",    "toggle"),
    ("AddLight_Button.png",          None,                                      "normal"),
]
_RIGHT_DEFS = [
    ("QuickPreset.png", None, "normal"),
    ("QuickPreset.png", None, "normal"),
    ("QuickPreset.png", None, "normal"),
]

# ── Page 2 scenes ──────────────────────────────────────────────────────────────
_SCENES = [
    ("Cozy Evening",  [(255, 130, 50),  (255,  90, 20),  (180,  50, 10)]),
    ("Focus",         [(160, 200, 255), (180, 215, 255), (140, 185, 255)]),
    ("Party",         [(170,  0, 255),  (255,  0, 140),  (0,  210, 255)]),
    ("Relax",         [(50,  90, 200),  (110,  70, 200), (60, 170, 150)]),
    ("Movie Night",   [(170,  15, 15),  (110,  35,  5),  (70,   5,  35)]),
    ("Morning",       [(255, 215,  90), (255, 170,  70), (235, 235, 190)]),
]

# ── Page 2 grid — 3 × 2 squares ───────────────────────────────────────────────
_COLS = 3
_ROWS = 2
_GX   = 12
_GY   = 12
_SQ   = min(
    (W         - _GX * (_COLS - 1)) // _COLS,
    (CONTENT_H - _GY * (_ROWS - 1)) // _ROWS,
)
_BM_X = (W         - _COLS * _SQ - _GX * (_COLS - 1)) // 2
_BM_Y = (CONTENT_H - _ROWS * _SQ - _GY * (_ROWS - 1)) // 2
_BR   = 24.0


# ── Data classes ───────────────────────────────────────────────────────────────

class _Light:
    """A light icon placed on the floorplan."""
    __slots__ = ("pos", "selected")

    def __init__(self, pos: QPointF):
        self.pos      = pos     # center, floorplan-relative coords
        self.selected = False


class _PresetBtn:
    __slots__ = ("pix_n", "pix_h", "mode", "rect", "pressed", "toggled")

    def __init__(self, pix_n, pix_h, mode, rect):
        self.pix_n   = pix_n
        self.pix_h   = pix_h
        self.mode    = mode
        self.rect    = rect
        self.pressed = False
        self.toggled = False

    @property
    def current_pix(self) -> QPixmap | None:
        if self.mode == "momentary" and self.pressed and self.pix_h:
            return self.pix_h
        if self.mode == "toggle"    and self.toggled and self.pix_h:
            return self.pix_h
        return self.pix_n


# ── Module-level helpers ───────────────────────────────────────────────────────

def _load_preset_pix(name: str) -> QPixmap | None:
    pix = QPixmap(str(ASSETS_DIR / name))
    if pix.isNull():
        return None
    w = int(pix.width() * _BTN_H / pix.height())
    return pix.scaled(w, _BTN_H,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _build_left_btns() -> list[_PresetBtn]:
    btns: list[_PresetBtn] = []
    x = float(PRESETS_X + _BTN_PAD)
    for fname_n, fname_h, mode in _LEFT_DEFS:
        pix_n = _load_preset_pix(fname_n)
        pix_h = _load_preset_pix(fname_h) if fname_h else None
        w     = pix_n.width() if pix_n else _BTN_H
        btns.append(_PresetBtn(pix_n, pix_h, mode, QRectF(x, PRESETS_Y + _BTN_PAD, w, _BTN_H)))
        x += w + _BTN_GAP
    return btns


def _build_right_btns() -> list[_PresetBtn]:
    btns: list[_PresetBtn] = []
    x = float(PRESETS_X + PRESETS_W - _BTN_PAD)
    for fname_n, fname_h, mode in reversed(_RIGHT_DEFS):
        pix_n = _load_preset_pix(fname_n)
        pix_h = _load_preset_pix(fname_h) if fname_h else None
        w     = pix_n.width() if pix_n else _BTN_H
        x    -= w
        btns.insert(0, _PresetBtn(pix_n, pix_h, mode, QRectF(x, PRESETS_Y + _BTN_PAD, w, _BTN_H)))
        x    -= _BTN_GAP
    return btns


def _scene_button_pixmap(size: int, name: str, colors: list) -> QPixmap:
    w = h = size
    pix = QPixmap(w, h)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    full_rect = QRectF(0, 0, w, h)
    path = QPainterPath()
    path.addRoundedRect(full_rect, _BR, _BR)

    p.setClipPath(path)
    p.fillPath(path, QColor(10, 10, 16))

    primary_pos = [(0.28, 0.28), (0.72, 0.28), (0.50, 0.75)]
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
        avg    = ((c0[0]+c1[0])//2, (c0[1]+c1[1])//2, (c0[2]+c1[2])//2)
        grad   = QRadialGradient(w * mx, h * my, mid_r)
        c      = QColor(*avg)
        grad.setColorAt(0.00, QColor(c.red(), c.green(), c.blue(), 120))
        grad.setColorAt(0.60, QColor(c.red(), c.green(), c.blue(),  40))
        grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(full_rect, grad)

    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for sw in (18, 13, 9, 5, 2):
        pen = QPen(QColor(255, 255, 255, 20))
        pen.setWidthF(float(sw))
        p.setPen(pen)
        p.drawPath(path)

    p.setClipping(False)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setFont(QFont("Inter", 13, QFont.Weight.Medium))
    p.setPen(QColor(0x2f, 0x2f, 0x2f))
    p.drawText(full_rect, Qt.AlignmentFlag.AlignCenter, name)
    p.end()
    return pix


# ── Main widget ────────────────────────────────────────────────────────────────

class LightsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._page          = 0
        self._drag_start_x: float | None = None
        self._pressed_btn:  _PresetBtn  | None = None

        # Light management
        self._lights:       list[_Light] = []
        self._dragging:     int | None   = None   # index into _lights
        self._drag_offset                = QPointF(0, 0)

        # Assets
        self._floorplan_pix  = QPixmap(str(ASSETS_DIR / "floorplan.png"))
        self._pager_active   = QPixmap(str(ASSETS_DIR / "PagerPerlActive.png"))
        self._pager_inactive = QPixmap(str(ASSETS_DIR / "PagerPerlInactive.png"))

        # Light icon pixmaps — one per (Selected/Default) × (True/False) combo
        self._light_pix: dict[str, QPixmap] = {}
        for sel in ("Default", "Selected"):
            for move in ("True", "False"):
                key  = f"{sel}_Default_{move}"
                raw  = QPixmap(str(ASSETS_DIR / f"{key}.png"))
                if not raw.isNull():
                    self._light_pix[key] = raw.scaled(
                        _LIGHT_SZ, _LIGHT_SZ,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

        self._left_btns  = _build_left_btns()
        self._right_btns = _build_right_btns()

        self._scene_pixmaps: list[QPixmap] = [
            _scene_button_pixmap(_SQ, name, colors)
            for name, colors in _SCENES
        ]

    # ── Light state helpers ───────────────────────────────────────────────────

    @property
    def _options_mode(self) -> bool:
        """True when the LightSettings toggle (left btn index 2) is active."""
        return self._left_btns[2].toggled

    def _light_pix_key(self, light: _Light) -> str:
        sel  = "Selected" if light.selected else "Default"
        move = "True"     if self._options_mode else "False"
        return f"{sel}_Default_{move}"

    def _light_rect(self, light: _Light) -> QRectF:
        half = _LIGHT_SZ / 2
        cx   = FLOORPLAN_X + light.pos.x()
        cy   = FLOORPLAN_Y + light.pos.y()
        return QRectF(cx - half, cy - half, _LIGHT_SZ, _LIGHT_SZ)

    def _deselect_all(self):
        for l in self._lights:
            l.selected = False

    # ── Button actions ────────────────────────────────────────────────────────

    def _on_btn_release(self, btn: _PresetBtn):
        """Dispatches side-effects after a button click is confirmed."""
        if btn is self._left_btns[2]:   # LightSettings toggle
            self._on_options_toggle()
        elif btn is self._left_btns[3]: # AddLight
            self._add_light()

    def _on_options_toggle(self):
        if not self._options_mode:      # just turned OFF
            self._dragging = None       # cancel any active drag
        self.update()

    def _add_light(self):
        """Place a new light at floorplan centre, select it, ensure options mode is on."""
        self._deselect_all()
        light          = _Light(QPointF(FLOORPLAN_W / 2, FLOORPLAN_H / 2))
        light.selected = True
        self._lights.append(light)
        self._left_btns[2].toggled = True   # force LightSettings toggle on
        self.update()

    # ── Interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()

        if self._page == 0:
            # 1. Preset buttons take priority
            for btn in self._left_btns + self._right_btns:
                if btn.rect.contains(pos):
                    self._pressed_btn = btn
                    if btn.mode == "momentary":
                        btn.pressed = True
                        self.update()
                    return

            # 2. Light icons on floorplan
            fp_rect = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)
            if fp_rect.contains(pos):
                for i, light in enumerate(self._lights):
                    if self._light_rect(light).contains(pos):
                        self._deselect_all()
                        light.selected = True
                        if self._options_mode:
                            self._dragging    = i
                            self._drag_offset = QPointF(
                                pos.x() - (FLOORPLAN_X + light.pos.x()),
                                pos.y() - (FLOORPLAN_Y + light.pos.y()),
                            )
                        self.update()
                        return
                # Tap on empty floorplan → deselect all
                self._deselect_all()
                self.update()
                return

        self._drag_start_x = pos.x()

    def mouseMoveEvent(self, ev):
        if self._dragging is not None:
            pos   = ev.position()
            light = self._lights[self._dragging]
            half  = _LIGHT_SZ / 2
            light.pos = QPointF(
                max(half, min(pos.x() - FLOORPLAN_X - self._drag_offset.x(), FLOORPLAN_W - half)),
                max(half, min(pos.y() - FLOORPLAN_Y - self._drag_offset.y(), FLOORPLAN_H - half)),
            )
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()

        if self._dragging is not None:
            self._dragging = None
            return

        if self._pressed_btn is not None:
            btn  = self._pressed_btn
            self._pressed_btn = None
            was_in = btn.rect.contains(pos)
            if btn.mode == "momentary":
                btn.pressed = False
            elif btn.mode == "toggle" and was_in:
                btn.toggled = not btn.toggled
            if was_in:
                self._on_btn_release(btn)
            self.update()
            return

        if self._drag_start_x is not None:
            delta = pos.x() - self._drag_start_x
            if abs(delta) > 60:
                new = self._page + (1 if delta < 0 else -1)
                if 0 <= new <= 1:
                    self._page = new
                    self.update()
            self._drag_start_x = None

    # ── Paint ─────────────────────────────────────────────────────────────────

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
        # Floorplan
        if not self._floorplan_pix.isNull():
            p.drawPixmap(FLOORPLAN_X, FLOORPLAN_Y, self._floorplan_pix)
        else:
            fp = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)
            p.fillRect(fp, QColor(55, 80, 130, 160))
            p.setPen(QColor(160, 190, 255, 200))
            p.setFont(QFont("Inter", 12))
            p.drawText(fp, Qt.AlignmentFlag.AlignCenter, "floorplan.png not found")

        # Light icons (drawn on top of floorplan)
        for light in self._lights:
            pix = self._light_pix.get(self._light_pix_key(light))
            if pix:
                r = self._light_rect(light)
                p.drawPixmap(int(r.x()), int(r.y()), pix)

        # Preset row buttons
        for btn in self._left_btns + self._right_btns:
            pix = btn.current_pix
            if pix:
                p.drawPixmap(int(btn.rect.x()), int(btn.rect.y()), pix)

        # Remaining gap below preset row
        gap_y = PRESETS_Y + PRESETS_H
        gap_h = CONTENT_H - gap_y
        if gap_h > 0:
            p.fillRect(QRectF(0, gap_y, W, gap_h), QColor(80, 80, 80, 30))

    def _draw_page2(self, p: QPainter):
        for idx, pix in enumerate(self._scene_pixmaps):
            col = idx % _COLS
            row = idx // _COLS
            p.drawPixmap(_BM_X + col * (_SQ + _GX), _BM_Y + row * (_SQ + _GY), pix)

    def _draw_pager(self, p: QPainter):
        n       = 2
        gap     = 12
        pw_a    = self._pager_active.width()    if not self._pager_active.isNull()   else 34
        pw_i    = self._pager_inactive.width()  if not self._pager_inactive.isNull() else 34
        ph_a    = self._pager_active.height()   if not self._pager_active.isNull()   else 17
        ph_i    = self._pager_inactive.height() if not self._pager_inactive.isNull() else 16
        sx      = (W - pw_a - gap - pw_i) // 2
        cy      = CONTENT_H + PAGER_H // 2

        for i in range(n):
            if i == self._page:
                pix, ph = self._pager_active, ph_a
            else:
                pix, ph = self._pager_inactive, ph_i
            if not pix.isNull():
                p.drawPixmap(sx + i * (pw_i + gap), cy - ph // 2, pix)


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
