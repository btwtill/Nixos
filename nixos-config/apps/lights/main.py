from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
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
FLOORPLAN_X = (W - FLOORPLAN_W) // 2   # 32
FLOORPLAN_Y = 8

PRESETS_W = 689
PRESETS_H = 73
PRESETS_X = (W - PRESETS_W) // 2
PRESETS_Y = FLOORPLAN_Y + FLOORPLAN_H + 5  # 366

_LIGHT_SZ = 40   # light icon display size (px)

# Side panel — right edge flush with floorplan right edge
PANEL_W     = 342
PANEL_H     = 447
PANEL_X     = FLOORPLAN_X + FLOORPLAN_W - PANEL_W  # 440
PANEL_Y     = FLOORPLAN_Y                           # 8
_PANEL_SLIDE = 50    # px off-screen offset when hidden
_FP_PAN_MIN = -280   # max left pan (px) when panel open
_FP_PAN_MAX = 0      # don't pan past default
_ANIM_EASE  = 0.18   # easing factor per frame (~60 fps)

# ── Preset row ─────────────────────────────────────────────────────────────────
_BTN_PAD = 8
_BTN_GAP = 10
_BTN_H   = PRESETS_H - _BTN_PAD * 2   # 57

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
    __slots__ = ("pos", "selected")
    def __init__(self, pos: QPointF):
        self.pos      = pos     # centre in floorplan-local coords
        self.selected = False


class _PresetBtn:
    __slots__ = ("pix_n", "pix_h", "mode", "rect", "pressed", "toggled")
    def __init__(self, pix_n, pix_h, mode, rect):
        self.pix_n, self.pix_h = pix_n, pix_h
        self.mode               = mode
        self.rect               = rect
        self.pressed            = False
        self.toggled            = False

    @property
    def current_pix(self) -> QPixmap | None:
        if self.mode == "momentary" and self.pressed and self.pix_h:
            return self.pix_h
        if self.mode == "toggle"    and self.toggled and self.pix_h:
            return self.pix_h
        return self.pix_n


# ── Module helpers ─────────────────────────────────────────────────────────────

def _load_preset_pix(name: str) -> QPixmap | None:
    pix = QPixmap(str(ASSETS_DIR / name))
    if pix.isNull():
        return None
    return pix.scaled(int(pix.width() * _BTN_H / pix.height()), _BTN_H,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _build_left_btns() -> list[_PresetBtn]:
    btns: list[_PresetBtn] = []
    x = float(PRESETS_X + _BTN_PAD)
    for fn, fh, mode in _LEFT_DEFS:
        pn = _load_preset_pix(fn)
        ph = _load_preset_pix(fh) if fh else None
        w  = pn.width() if pn else _BTN_H
        btns.append(_PresetBtn(pn, ph, mode, QRectF(x, PRESETS_Y + _BTN_PAD, w, _BTN_H)))
        x += w + _BTN_GAP
    return btns


def _build_right_btns() -> list[_PresetBtn]:
    btns: list[_PresetBtn] = []
    x = float(PRESETS_X + PRESETS_W - _BTN_PAD)
    for fn, fh, mode in reversed(_RIGHT_DEFS):
        pn = _load_preset_pix(fn)
        ph = _load_preset_pix(fh) if fh else None
        w  = pn.width() if pn else _BTN_H
        x -= w
        btns.insert(0, _PresetBtn(pn, ph, mode, QRectF(x, PRESETS_Y + _BTN_PAD, w, _BTN_H)))
        x -= _BTN_GAP
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
        [(colors[0], colors[1]), (colors[1], colors[2]), (colors[0], colors[2])],
    ):
        avg  = ((c0[0]+c1[0])//2, (c0[1]+c1[1])//2, (c0[2]+c1[2])//2)
        grad = QRadialGradient(w*(p0[0]+p1[0])/2, h*(p0[1]+p1[1])/2, mid_r)
        c    = QColor(*avg)
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

        self._page         = 0
        self._drag_start_x: float | None = None
        self._pressed_btn:  _PresetBtn   | None = None

        # Light state
        self._lights:   list[_Light] = []
        self._dragging: int | None   = None
        self._drag_offset            = QPointF(0, 0)

        # Floorplan pan
        self._fp_offset_x: float     = 0.0   # current rendered offset (px, ≤ 0)
        self._fp_offset_target: float = 0.0  # animation target
        self._fp_pan_start_x: float | None  = None
        self._fp_pan_offset_start: float    = 0.0

        # Side panel animation
        self._panel_progress: float = 0.0   # 0 = hidden, 1 = fully shown
        self._panel_target:   float = 0.0

        # Animation timer (~60 fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._animate)

        # Assets
        self._floorplan_pix  = QPixmap(str(ASSETS_DIR / "floorplan.png"))
        self._panel_pix      = QPixmap(str(ASSETS_DIR / "LightsSidePanelBackground.png"))
        self._pager_active   = QPixmap(str(ASSETS_DIR / "PagerPerlActive.png"))
        self._pager_inactive = QPixmap(str(ASSETS_DIR / "PagerPerlInactive.png"))

        self._light_pix: dict[str, QPixmap] = {}
        for sel in ("Default", "Selected"):
            for move in ("True", "False"):
                key = f"{sel}_Default_{move}"
                raw = QPixmap(str(ASSETS_DIR / f"{key}.png"))
                if not raw.isNull():
                    self._light_pix[key] = raw.scaled(
                        _LIGHT_SZ, _LIGHT_SZ,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

        self._left_btns  = _build_left_btns()
        self._right_btns = _build_right_btns()

        self._scene_pixmaps: list[QPixmap] = [
            _scene_button_pixmap(_SQ, name, colors) for name, colors in _SCENES
        ]

    # ── Animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        done = True

        dp = self._panel_target - self._panel_progress
        if abs(dp) > 0.007:
            self._panel_progress += dp * _ANIM_EASE
            done = False
        else:
            self._panel_progress = self._panel_target

        df = self._fp_offset_target - self._fp_offset_x
        if abs(df) > 0.4:
            self._fp_offset_x += df * _ANIM_EASE
            done = False
        else:
            self._fp_offset_x = self._fp_offset_target

        if done:
            self._anim_timer.stop()
        self.update()

    # ── Panel / floorplan state helpers ───────────────────────────────────────

    def _any_selected(self) -> bool:
        return any(l.selected for l in self._lights)

    def _update_panel_state(self, newly_selected: _Light | None = None):
        """Call after any selection change. Animates panel in/out and auto-pans."""
        was_open = self._panel_target > 0.5
        any_sel  = self._any_selected()
        self._panel_target = 1.0 if any_sel else 0.0

        if any_sel:
            # Auto-pan so the relevant light isn't hidden behind the panel
            light = newly_selected or next((l for l in self._lights if l.selected), None)
            if light is not None:
                self._auto_pan_for(light)
        else:
            self._fp_offset_target = 0.0   # return to default when panel closes

        self._anim_timer.start()

    def _auto_pan_for(self, light: _Light):
        """If the light is behind the panel, shift the floorplan left to reveal it."""
        light_screen_x = FLOORPLAN_X + light.pos.x() + self._fp_offset_x
        # The panel covers [PANEL_X, PANEL_X + PANEL_W] on screen.
        # We want the light centre to be at least (PANEL_X - _LIGHT_SZ) to stay visible.
        visible_limit = PANEL_X - _LIGHT_SZ
        if light_screen_x > visible_limit:
            shift = visible_limit - (FLOORPLAN_X + light.pos.x())
            self._fp_offset_target = max(_FP_PAN_MIN, shift)
        # If already visible, leave the offset as-is so the user's pan is not reset

    def _fp_pan_limits(self) -> tuple[float, float]:
        lo = _FP_PAN_MIN if self._panel_target > 0.1 else 0.0
        return lo, _FP_PAN_MAX

    # ── Light state helpers ───────────────────────────────────────────────────

    @property
    def _options_mode(self) -> bool:
        return self._left_btns[2].toggled

    def _light_pix_key(self, light: _Light) -> str:
        sel  = "Selected" if light.selected else "Default"
        move = "True"     if self._options_mode else "False"
        return f"{sel}_Default_{move}"

    def _light_rect(self, light: _Light) -> QRectF:
        half = _LIGHT_SZ / 2
        cx   = FLOORPLAN_X + light.pos.x() + self._fp_offset_x
        cy   = FLOORPLAN_Y + light.pos.y()
        return QRectF(cx - half, cy - half, _LIGHT_SZ, _LIGHT_SZ)

    def _deselect_all(self):
        for l in self._lights:
            l.selected = False

    # ── Button actions ────────────────────────────────────────────────────────

    def _on_btn_release(self, btn: _PresetBtn):
        if btn is self._left_btns[2]:    # LightSettings toggle
            if not self._options_mode:   # just turned OFF — cancel drag
                self._dragging = None
            self.update()
        elif btn is self._left_btns[3]:  # AddLight
            self._deselect_all()
            light          = _Light(QPointF(FLOORPLAN_W / 2, FLOORPLAN_H / 2))
            light.selected = True
            self._lights.append(light)
            self._left_btns[2].toggled = True   # force options mode on
            self._update_panel_state(newly_selected=light)

    # ── Interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()

        if self._page == 0:
            # 1. Preset buttons
            for btn in self._left_btns + self._right_btns:
                if btn.rect.contains(pos):
                    self._pressed_btn = btn
                    if btn.mode == "momentary":
                        btn.pressed = True
                        self.update()
                    return

            # 2. Floorplan area
            fp_rect = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)
            if fp_rect.contains(pos):
                for i, light in enumerate(self._lights):
                    if self._light_rect(light).contains(pos):
                        if self._options_mode:
                            # In movable state: always select and start drag;
                            # tapping again does NOT deselect.
                            light.selected = True
                            self._dragging    = i
                            self._drag_offset = QPointF(
                                pos.x() - (FLOORPLAN_X + light.pos.x() + self._fp_offset_x),
                                pos.y() - (FLOORPLAN_Y + light.pos.y()),
                            )
                        else:
                            # Normal state: tap toggles selection.
                            light.selected = not light.selected
                        self._update_panel_state(
                            newly_selected=light if light.selected else None
                        )
                        return
                # Tap on empty floorplan → begin pan tracking (resolve on release)
                self._fp_pan_start_x      = pos.x()
                self._fp_pan_offset_start = self._fp_offset_x
                return

        self._drag_start_x = pos.x()

    def mouseMoveEvent(self, ev):
        pos = ev.position()

        if self._dragging is not None:
            half  = _LIGHT_SZ / 2
            light = self._lights[self._dragging]
            light.pos = QPointF(
                max(half, min(
                    pos.x() - FLOORPLAN_X - self._fp_offset_x - self._drag_offset.x(),
                    FLOORPLAN_W - half,
                )),
                max(half, min(
                    pos.y() - FLOORPLAN_Y - self._drag_offset.y(),
                    FLOORPLAN_H - half,
                )),
            )
            self.update()
            return

        if self._fp_pan_start_x is not None:
            delta = pos.x() - self._fp_pan_start_x
            lo, hi = self._fp_pan_limits()
            self._fp_offset_x      = max(lo, min(hi, self._fp_pan_offset_start + delta))
            self._fp_offset_target = self._fp_offset_x   # follow finger exactly
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()

        if self._dragging is not None:
            self._dragging = None
            return

        if self._fp_pan_start_x is not None:
            delta = pos.x() - self._fp_pan_start_x
            if abs(delta) < 8:       # was a tap, not a pan → deselect all
                self._deselect_all()
                self._update_panel_state()
            self._fp_pan_start_x = None
            return

        if self._pressed_btn is not None:
            btn     = self._pressed_btn
            self._pressed_btn = None
            was_in  = btn.rect.contains(pos)
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
        fp_clip = QRectF(FLOORPLAN_X, FLOORPLAN_Y, FLOORPLAN_W, FLOORPLAN_H)

        # ── Floorplan image (clipped, panned) ─────────────────────────────────
        p.save()
        p.setClipRect(fp_clip)
        if not self._floorplan_pix.isNull():
            p.drawPixmap(int(FLOORPLAN_X + self._fp_offset_x), FLOORPLAN_Y,
                         self._floorplan_pix)
        else:
            p.fillRect(fp_clip, QColor(55, 80, 130, 160))
            p.setPen(QColor(160, 190, 255, 200))
            p.setFont(QFont("Inter", 12))
            p.drawText(fp_clip, Qt.AlignmentFlag.AlignCenter, "floorplan.png not found")

        # ── Light icons (clipped to floorplan, panned with it) ────────────────
        for light in self._lights:
            pix = self._light_pix.get(self._light_pix_key(light))
            if pix:
                r = self._light_rect(light)
                p.drawPixmap(int(r.x()), int(r.y()), pix)
        p.restore()

        # ── Preset row buttons ─────────────────────────────────────────────────
        for btn in self._left_btns + self._right_btns:
            pix = btn.current_pix
            if pix:
                p.drawPixmap(int(btn.rect.x()), int(btn.rect.y()), pix)

        # ── Side panel — drawn last so it covers floorplan AND preset row ──────
        if self._panel_progress > 0.001 and not self._panel_pix.isNull():
            slide_x = int((1.0 - self._panel_progress) * _PANEL_SLIDE)
            p.save()
            p.setOpacity(self._panel_progress)
            p.drawPixmap(PANEL_X + slide_x, PANEL_Y, self._panel_pix)
            p.restore()

        # Remaining gap
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
        n     = 2
        gap   = 12
        pw_a  = self._pager_active.width()    if not self._pager_active.isNull()   else 34
        pw_i  = self._pager_inactive.width()  if not self._pager_inactive.isNull() else 34
        ph_a  = self._pager_active.height()   if not self._pager_active.isNull()   else 17
        ph_i  = self._pager_inactive.height() if not self._pager_inactive.isNull() else 16
        sx    = (W - pw_a - gap - pw_i) // 2
        cy    = CONTENT_H + PAGER_H // 2
        for i in range(n):
            pix, ph = (self._pager_active, ph_a) if i == self._page \
                      else (self._pager_inactive, ph_i)
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
