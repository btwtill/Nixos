"""Theme Lab — fine-tune colours on the device.

Edits a single theme, the test theme ("test"), through the homy-theme service.
Built-in themes stay untouched: start the test theme as a copy of one of them,
tune each token, preview it on the whole UI, then copy the JSON into
apps/theme/themes.json to make it a built-in.

Install:   homy-apps install ~/Nixos/nixos-config/app-store/theme-lab
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

SERVICE = "http://127.0.0.1:47820"
TEST_ID, TEST_NAME = "test", "Test theme"
W, H = 814, 490

BG, CARD, CARD_ALT = "#1E1E1E", "#2A2A2A", "#333333"
TEXT, TEXT_SEC, ACCENT = "#EAEAEA", "#8A8A8A", "#3DAEE9"


def api(method: str, path: str, body=None):
    req = urllib.request.Request(SERVICE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read()).get("error", str(e))}


def osk(command: str):
    try:
        subprocess.Popen(["osk", command])
    except OSError:
        pass


def button(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(36)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    bg, fg = (ACCENT, BG) if primary else (CARD_ALT, TEXT)
    b.setStyleSheet(f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 18px;"
                    f" padding: 0 14px; font-size: 13px; font-weight: bold; }}"
                    f"QPushButton:pressed {{ background: {TEXT}; color: {BG}; }}")
    return b


class HexEdit(QLineEdit):
    """Hex field that brings up the on-screen keyboard when tapped."""
    def focusInEvent(self, e):
        super().focusInEvent(e)
        osk("show")

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        osk("hide")


class TokenRow(QFrame):
    def __init__(self, name: str, description: str, on_select):
        super().__init__()
        self.name = name
        self.setFixedHeight(48)
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        self.swatch = QLabel()
        self.swatch.setFixedSize(30, 30)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel(name)
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px;")
        sub = QLabel(description)
        sub.setStyleSheet(f"color: {TEXT_SEC}; font-size: 10px;")
        text.addWidget(title)
        text.addWidget(sub)
        self.hex = QLabel()
        self.hex.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px; font-family: monospace;")
        lay.addWidget(self.swatch)
        lay.addLayout(text, 1)
        lay.addWidget(self.hex)
        self._on_select = on_select
        self.set_selected(False)

    def set_color(self, hex_: str):
        self.swatch.setStyleSheet(f"background: {hex_}; border: 1px solid {CARD_ALT}; border-radius: 6px;")
        self.hex.setText(hex_)

    def set_selected(self, on: bool):
        border = ACCENT if on else CARD
        self.setStyleSheet(f"#row {{ background: {CARD}; border: 1px solid {border}; border-radius: 8px; }}"
                           "QLabel { background: transparent; }")

    def mousePressEvent(self, e):
        self._on_select(self.name)


class ThemeLab(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(W, H)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BG}; }} QLabel {{ color: {TEXT}; }}"
                           f"QComboBox {{ background: {CARD_ALT}; color: {TEXT}; border: none; border-radius: 8px;"
                           f" padding: 6px 10px; font-size: 13px; }}")
        self.tokens: dict[str, str] = {}
        self.descriptions: dict[str, str] = {}
        self.current = ""
        self.previous_active = ""
        self.save_timer = QTimer(self, singleShot=True, interval=150, timeout=self._save)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Theme Lab")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(QLabel("Copy from"))
        self.base = QComboBox()
        self.base.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        head.addWidget(self.base)
        copy_btn = button("Copy")
        copy_btn.clicked.connect(self._copy_from)
        head.addWidget(copy_btn)
        root.addLayout(head)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px;")
        root.addWidget(self.status)

        body = QHBoxLayout()
        body.setSpacing(12)
        # token list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}")
        holder = QWidget()
        self.list = QVBoxLayout(holder)
        self.list.setContentsMargins(0, 0, 6, 0)
        self.list.setSpacing(6)
        scroll.setWidget(holder)
        body.addWidget(scroll, 1)
        # editor
        editor = QFrame()
        editor.setObjectName("editor")
        editor.setStyleSheet(f"#editor {{ background: {CARD}; border-radius: 10px; }} QLabel {{ background: transparent; }}")
        ed = QVBoxLayout(editor)
        ed.setContentsMargins(14, 12, 14, 12)
        self.big = QLabel()
        self.big.setFixedHeight(70)
        self.token_label = QLabel("")
        self.token_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        ed.addWidget(self.token_label)
        ed.addWidget(self.big)
        grid = QGridLayout()
        self.sliders = []
        for i, ch in enumerate("RGBA"):
            lbl = QLabel(ch)
            lbl.setStyleSheet(f"color: {TEXT_SEC};")
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 255)
            sl.setFixedHeight(32)
            sl.setStyleSheet(f"QSlider::groove:horizontal {{ height: 8px; background: {CARD_ALT}; border-radius: 4px; }}"
                             f"QSlider::handle:horizontal {{ width: 26px; margin: -10px 0; border-radius: 13px; background: {TEXT}; }}")
            sl.valueChanged.connect(self._from_sliders)
            val = QLabel("0")
            val.setFixedWidth(30)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(sl, i, 1)
            grid.addWidget(val, i, 2)
            self.sliders.append((sl, val))
        ed.addLayout(grid)
        hexrow = QHBoxLayout()
        hexrow.addWidget(QLabel("Hex"))
        self.hex = HexEdit()
        self.hex.setMaxLength(9)
        self.hex.setStyleSheet(f"background: {BG}; color: {TEXT}; border: 1px solid {CARD_ALT}; border-radius: 8px;"
                               " padding: 6px 10px; font-size: 15px; font-family: monospace;")
        self.hex.editingFinished.connect(self._from_hex)
        hexrow.addWidget(self.hex, 1)
        ed.addLayout(hexrow)
        ed.addStretch(1)
        body.addWidget(editor, 1)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        self.preview_btn = button("Preview on device", primary=True)
        self.preview_btn.clicked.connect(self._toggle_preview)
        json_btn = button("Copy JSON")
        json_btn.clicked.connect(self._copy_json)
        foot.addWidget(self.preview_btn)
        foot.addStretch(1)
        foot.addWidget(json_btn)
        root.addLayout(foot)

        self.rows: dict[str, TokenRow] = {}
        self._load()

    # ── data ──────────────────────────────────────────────────────────────────
    def _load(self):
        try:
            self.descriptions = api("GET", "/tokens")
            listing = api("GET", "/themes")
        except OSError:
            self.status.setText("The theme service (homy-theme) isn't running.")
            return
        ids = [t["id"] for t in listing["themes"]]
        self.base.clear()
        for t in listing["themes"]:
            if t["id"] != TEST_ID:
                self.base.addItem(t["name"], t["id"])
        active = listing["active"]
        if TEST_ID not in ids:                                   # first start: copy the active theme
            src = api("GET", f"/themes/{active}")
            api("PUT", f"/themes/{TEST_ID}", {"name": TEST_NAME, "tokens": src["tokens"]})
        self.previous_active = active if active != TEST_ID else "dark"
        self.tokens = api("GET", f"/themes/{TEST_ID}")["tokens"]
        for name, desc in self.descriptions.items():
            row = TokenRow(name, desc, self._select)
            self.rows[name] = row
            self.list.addWidget(row)
        self.list.addStretch(1)
        self._refresh_rows()
        self._select(next(iter(self.descriptions)))
        self._update_preview_button(active == TEST_ID)

    def _refresh_rows(self):
        for name, row in self.rows.items():
            row.set_color(self.tokens.get(name, "#000000"))

    def _save(self):
        res = api("PUT", f"/themes/{TEST_ID}", {"name": TEST_NAME, "tokens": self.tokens})
        self.status.setText(res.get("error", "") or "Saved to the test theme.")

    # ── editing ───────────────────────────────────────────────────────────────
    def _select(self, name: str):
        self.current = name
        for n, row in self.rows.items():
            row.set_selected(n == name)
        self.token_label.setText(name)
        self._show(self.tokens[name])

    @staticmethod
    def _rgba(hex_: str) -> tuple[int, int, int, int]:
        """#RRGGBB or #RRGGBBAA → (r, g, b, a)."""
        v = hex_.lstrip("#")
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), int(v[6:8], 16) if len(v) == 8 else 255

    def _show(self, hex_: str):
        r, g, b, a = self._rgba(hex_)
        for (sl, val), v in zip(self.sliders, (r, g, b, a)):
            sl.blockSignals(True)
            sl.setValue(v)
            sl.blockSignals(False)
            val.setText(str(v))
        self.hex.setText(hex_.upper())
        self.big.setStyleSheet(f"background: rgba({r}, {g}, {b}, {a}); border-radius: 8px;")

    def _set(self, hex_: str):
        self.tokens[self.current] = hex_.upper()
        self._show(hex_)
        self.rows[self.current].set_color(hex_.upper())
        self.save_timer.start()

    def _from_sliders(self):
        r, g, b, a = (sl.value() for sl, _ in self.sliders)
        self._set(f"#{r:02X}{g:02X}{b:02X}" + (f"{a:02X}" if a != 255 else ""))

    def _from_hex(self):
        text = self.hex.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) in (7, 9) and all(c in "0123456789abcdefABCDEF" for c in text[1:]):
            self._set(text)
        else:
            self.status.setText(f"'{self.hex.text()}' is not a #RRGGBB or #RRGGBBAA colour.")

    def _copy_from(self):
        src = api("GET", f"/themes/{self.base.currentData()}")
        self.tokens = dict(src["tokens"])
        self._refresh_rows()
        self._select(self.current)
        self._save()

    # ── preview / export ──────────────────────────────────────────────────────
    def _toggle_preview(self):
        active = api("GET", "/themes")["active"]
        if active == TEST_ID:
            api("POST", "/active", {"id": self.previous_active})
        else:
            self.previous_active = active
            api("POST", "/active", {"id": TEST_ID})
        self._update_preview_button(active != TEST_ID)

    def _update_preview_button(self, previewing: bool):
        self.preview_btn.setText(f"Back to {self.previous_active}" if previewing else "Preview on device")

    def _copy_json(self):
        theme = {"id": "my-theme", "name": "My theme", "tokens": self.tokens}
        QGuiApplication.clipboard().setText(json.dumps(theme, indent=2))
        self.status.setText("Copied — paste it into apps/theme/themes.json (change id and name).")


def main():
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("Theme Lab")
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    win.setCentralWidget(ThemeLab())
    win.setFixedSize(W, H)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
