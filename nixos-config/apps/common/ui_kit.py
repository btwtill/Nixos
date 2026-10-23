"""Placeholder UI building blocks shared by the Bluetooth and Wi-Fi apps.

Everything visual lives here so the Figma designs can replace it in one place:
colours, the page frame, section headers, list rows and buttons.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScroller,
    QVBoxLayout, QWidget,
)

# Same canvas as the other apps
W, H = 814, 490

BG       = "#1E1E1E"
CARD     = "#2A2A2A"
CARD_ALT = "#333333"
TEXT     = "#EAEAEA"
TEXT_SEC = "#8A8A8A"
ACCENT   = "#3DAEE9"
OK       = "#4CAF50"
BAD      = "#E05555"

ROW_H = 52


class Page(QWidget):
    """Fixed-size root: title row (title + action buttons) and a scrollable list.

    Use add_action() for header buttons, set_status() for the line under the
    title, and clear_list()/add_section()/add_row() to fill the list.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#page {{ background: {BG}; }} QLabel {{ color: {TEXT}; background: transparent; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(self._title)
        header.addStretch(1)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        header.addLayout(self._actions)
        root.addLayout(header)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {TEXT_SEC}; font-size: 13px;")
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}"
            f"QScrollBar:vertical {{ background: {BG}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {CARD_ALT}; border-radius: 3px; }}"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )
        # Touch panel: drag anywhere to scroll.
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        self._list = QWidget()
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 8, 0)
        self._list_lay.setSpacing(6)
        scroll.setWidget(self._list)
        root.addWidget(scroll, 1)

    def add_action(self, button: QPushButton):
        self._actions.addWidget(button)

    def set_status(self, text: str):
        self._status.setText(text)

    def clear_list(self):
        while (item := self._list_lay.takeAt(0)) is not None:
            if item.widget():
                item.widget().deleteLater()

    def add_section(self, text: str):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; letter-spacing: 1px; padding: 10px 2px 2px 2px;")
        self._list_lay.addWidget(lbl)

    def add_note(self, text: str):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 13px; padding: 4px 2px;")
        self._list_lay.addWidget(lbl)

    def add_row(self, row: QWidget):
        self._list_lay.addWidget(row)

    def finish_list(self):
        self._list_lay.addStretch(1)


def button(text: str, primary: bool = False, danger: bool = False) -> QPushButton:
    """Pill button, sized for touch."""
    btn = QPushButton(text)
    btn.setFixedHeight(36)
    btn.setMinimumWidth(96)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    bg, fg = (ACCENT, BG) if primary else (CARD_ALT, TEXT)
    if danger:
        fg = BAD
    btn.setStyleSheet(
        f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 18px;"
        f" padding: 0 16px; font-size: 13px; font-weight: bold; }}"
        f"QPushButton:pressed {{ background: {ACCENT if not primary else TEXT}; color: {BG}; }}"
        f"QPushButton:checked {{ background: {ACCENT}; color: {BG}; }}"
        f"QPushButton:disabled {{ color: {TEXT_SEC}; }}"
    )
    return btn


class Row(QFrame):
    """List row: placeholder icon glyph, title + subtitle, action buttons."""

    def __init__(self, glyph: str, title: str, subtitle: str = "",
                 highlight: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ROW_H)
        self.setObjectName("row")
        border = f"border: 1px solid {ACCENT};" if highlight else "border: none;"
        self.setStyleSheet(
            f"#row {{ background: {CARD}; border-radius: 10px; {border} }}"
            "QLabel { background: transparent; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(12)

        icon = QLabel(glyph)
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"color: {ACCENT if highlight else TEXT_SEC}; font-size: 18px;")
        lay.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet(f"color: {TEXT}; font-size: 15px;")
        text.addWidget(name)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px;")
            text.addWidget(sub)
        lay.addLayout(text, 1)

        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(6)
        lay.addLayout(self._buttons)

    def add_button(self, btn: QPushButton) -> QPushButton:
        self._buttons.addWidget(btn)
        return btn
