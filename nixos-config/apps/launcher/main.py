"""App menu: a paged grid of installed launcher apps (see registry.py).

Tapping an app starts it with HOMY_APP_ID set; Qtile's config spots that
variable on the new window and gives the app its own group ("app:<id>").
Tapping an app that is already running switches to its group instead.
"""
from __future__ import annotations

import math
import os
import shlex
import subprocess
import sys

from PyQt6.QtCore import QFileSystemWatcher, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QVBoxLayout, QWidget,
)

import registry

W, H = 814, 490
COLS, ROWS = 4, 2
TILE_W, TILE_H = 150, 150
ICON = 96
SWIPE_PX = 60

BG       = "#1E1E1E"
CARD     = "#2A2A2A"
CARD_ALT = "#333333"
TEXT     = "#EAEAEA"
TEXT_SEC = "#8A8A8A"
ACCENT   = "#3DAEE9"


def _osk(command: str):
    try:
        subprocess.Popen(["osk", command])
    except OSError:
        pass


class SearchEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        _osk("show")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        _osk("hide")


class Tile(QWidget):
    """Placeholder app tile: rounded icon square + name. Mouse handling is done
    by the Pager (so a swipe that starts on a tile still pages)."""

    def __init__(self, app: registry.App, parent=None):
        super().__init__(parent)
        self.app = app
        self.pressed = False
        self.setFixedSize(TILE_W, TILE_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pix = QPixmap(app.icon) if app.icon else QPixmap()
        self._icon = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation) if not pix.isNull() else None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF((TILE_W - ICON) / 2, 8, ICON, ICON)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT if self.pressed else CARD))
        p.drawRoundedRect(box, 22, 22)
        if self._icon:
            p.drawPixmap(int(box.center().x() - self._icon.width() / 2),
                         int(box.center().y() - self._icon.height() / 2), self._icon)
        else:
            p.setPen(QColor(BG if self.pressed else TEXT_SEC))
            p.setFont(QFont("sans", 34, QFont.Weight.Bold))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.app.name[:1].upper())
        p.setPen(QColor(TEXT))
        p.setFont(QFont("sans", 13))
        p.drawText(QRectF(0, box.bottom() + 8, TILE_W, 30),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   p.fontMetrics().elidedText(self.app.name, Qt.TextElideMode.ElideRight, TILE_W - 8))


class Pager(QWidget):
    """Grid of tiles split into pages; swipe left/right to change page."""

    def __init__(self, on_launch, parent=None):
        super().__init__(parent)
        self._on_launch = on_launch
        self._tiles: list[Tile] = []
        self._page = 0
        self._press: QPointF | None = None
        self._pressed_tile: Tile | None = None
        self._empty_text = ""

    @property
    def pages(self) -> int:
        return max(1, math.ceil(len(self._tiles) / (COLS * ROWS)))

    def set_apps(self, apps: list[registry.App], empty_text: str):
        for t in self._tiles:
            t.hide()              # deleteLater only runs on the next loop pass
            t.deleteLater()
        self._tiles = [Tile(a, self) for a in apps]
        self._empty_text = empty_text
        self._page = min(self._page, self.pages - 1)
        self._layout_tiles()
        self.update()

    def _layout_tiles(self):
        per_page = COLS * ROWS
        grid_h = self.height() - 30                       # room for the page dots
        cell_w, cell_h = self.width() / COLS, grid_h / ROWS
        for i, tile in enumerate(self._tiles):
            page, slot = divmod(i, per_page)
            row, col = divmod(slot, COLS)
            tile.move(int(col * cell_w + (cell_w - TILE_W) / 2),
                      int(row * cell_h + (cell_h - TILE_H) / 2))
            tile.setVisible(page == self._page)

    def resizeEvent(self, _):
        self._layout_tiles()

    def _go(self, page: int):
        page = max(0, min(self.pages - 1, page))
        if page != self._page:
            self._page = page
            self._layout_tiles()
            self.update()

    def _tile_at(self, pos: QPointF) -> Tile | None:
        for t in self._tiles:
            if t.isVisible() and t.geometry().contains(pos.toPoint()):
                return t
        return None

    def mousePressEvent(self, ev):
        self._press = ev.position()
        self._pressed_tile = self._tile_at(ev.position())
        if self._pressed_tile:
            self._pressed_tile.pressed = True
            self._pressed_tile.update()

    def mouseMoveEvent(self, ev):
        # Once the finger moves like a swipe, it's no longer a tap on the tile.
        if self._press and self._pressed_tile and abs(ev.position().x() - self._press.x()) > SWIPE_PX / 2:
            self._release_tile()

    def mouseReleaseEvent(self, ev):
        if self._press is None:
            return
        dx = ev.position().x() - self._press.x()
        tile = self._pressed_tile
        self._release_tile()
        self._press = None
        if dx <= -SWIPE_PX:
            self._go(self._page + 1)
        elif dx >= SWIPE_PX:
            self._go(self._page - 1)
        elif tile and tile is self._tile_at(ev.position()):
            self._on_launch(tile.app)

    def _release_tile(self):
        if self._pressed_tile:
            self._pressed_tile.pressed = False
            self._pressed_tile.update()
            self._pressed_tile = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._tiles:
            p.setPen(QColor(TEXT_SEC))
            p.setFont(QFont("sans", 13))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self._empty_text)
            return
        if self.pages > 1:                                # page dots
            y = self.height() - 15
            x0 = self.width() / 2 - (self.pages - 1) * 9
            for i in range(self.pages):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACCENT if i == self._page else CARD_ALT))
                p.drawEllipse(QPointF(x0 + i * 18, y), 4, 4)


class Launcher(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#root {{ background: {BG}; }}"
            f"QLabel {{ color: {TEXT_SEC}; background: transparent; }}"
            f"QLineEdit {{ background: {CARD}; color: {TEXT}; border: none; border-radius: 18px;"
            f" padding: 0 16px; font-size: 15px; }}"
            f"QPushButton {{ background: {CARD}; color: {TEXT_SEC}; border: none; border-radius: 18px;"
            f" padding: 0 18px; font-size: 14px; }}"
            f"QPushButton:checked {{ background: {CARD_ALT}; color: {ACCENT}; }}"
        )
        self._apps: list[registry.App] = []
        self._category = "All"
        self._procs: dict[str, subprocess.Popen] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._search = SearchEdit()
        self._search.setPlaceholderText("Search apps")
        self._search.setFixedHeight(36)
        self._search.setClearButtonEnabled(True)
        # Only focus (and pop up the keyboard) when tapped, not when the menu opens.
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.textChanged.connect(self._render)
        header.addWidget(self._search, 1)
        self._chips = QHBoxLayout()
        self._chips.setSpacing(6)
        header.addLayout(self._chips)
        root.addLayout(header)

        self._pager = Pager(self._launch)
        # Tapping the grid takes focus from the search field, hiding the keyboard.
        self._pager.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        root.addWidget(self._pager, 1)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFixedHeight(18)
        root.addWidget(self._status)

        # Pick up installs/removals: watch the app folders, and re-scan
        # periodically for things a watcher can't see (nix profile switches).
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda _: self._reload())
        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self._reload)
        self._timer.start()
        self._reload(force=True)

    # ── data ──────────────────────────────────────────────────────────────────

    def _reload(self, force: bool = False):
        dirs = registry.watched_dirs()
        missing = [d for d in dirs if d not in self._watcher.directories()]
        if missing:
            self._watcher.addPaths(missing)
        apps = registry.discover()
        if apps != self._apps or force:
            self._apps = apps
            self._rebuild_chips()
            self._render()

    def _rebuild_chips(self):
        while (item := self._chips.takeAt(0)) is not None:
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        cats = ["All"] + sorted({a.category for a in self._apps})
        if self._category not in cats:
            self._category = "All"
        for cat in cats if len(cats) > 2 else ["All"]:
            chip = QPushButton(cat)
            chip.setCheckable(True)
            chip.setChecked(cat == self._category)
            chip.setFixedHeight(36)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.clicked.connect(lambda _=False, c=cat: self._set_category(c))
            self._chips.addWidget(chip)

    def _set_category(self, cat: str):
        self._category = cat
        self._rebuild_chips()
        self._render()

    def _render(self):
        q = self._search.text().strip().lower()
        shown = [a for a in self._apps
                 if (self._category == "All" or a.category == self._category)
                 and (not q or q in a.name.lower() or q in a.category.lower())]
        if not self._apps:
            empty = "No apps installed yet.\nInstall one with:  homy-apps install <folder or git URL>"
        else:
            empty = "No apps match."
        self._pager.set_apps(shown, empty)

    # ── launching ─────────────────────────────────────────────────────────────

    def _launch(self, app: registry.App):
        proc = self._procs.get(app.id)
        if proc and proc.poll() is None:
            # Already running — bring its group to the front.
            subprocess.Popen(["qtile", "cmd-obj", "-o", "group", f"app:{app.id}", "-f", "toscreen"])
            return
        env = dict(os.environ, HOMY_APP_ID=app.id)
        try:
            self._procs[app.id] = subprocess.Popen(
                shlex.split(app.exec), cwd=app.dir, env=env, start_new_session=True)
            self._status.setText("")
        except OSError as e:
            self._status.setText(f"Could not start {app.name}: {e.strerror or e}")


class LauncherApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Apps")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setCentralWidget(Launcher())
        self.setFixedSize(W, H)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Apps")
    window = LauncherApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
