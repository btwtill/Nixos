"""Page 1 — our apps, watched services, failed units and everything else running."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QScroller, QVBoxLayout, QWidget,
)

import config
from collectors import AppStatus, ServicesSnapshot, UnitStatus, fmt_bytes
from widgets.placeholders import StatusDot

ROW_H = 40


class _Row(QFrame):
    def __init__(self, state: str, label: str, detail: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ROW_H)
        self.setObjectName("row")
        self.setStyleSheet(
            f"#row {{ background: {config.CARD}; border-radius: 8px; }}"
            f"QLabel {{ background: transparent; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 14, 0)
        lay.setSpacing(10)
        dot = StatusDot()
        dot.set_state(state)
        name = QLabel(label)
        name.setStyleSheet(f"color: {config.TEXT}; font-size: 14px;")
        info = QLabel(detail)
        info.setStyleSheet(f"color: {config.TEXT_SEC}; font-size: 12px;")
        lay.addWidget(dot)
        lay.addWidget(name, 1)
        lay.addWidget(info)


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {config.TEXT_SEC}; font-size: 11px; letter-spacing: 1px;"
        "padding: 10px 2px 2px 2px; background: transparent;"
    )
    return lbl


def _unit_row(u: UnitStatus) -> _Row:
    detail = "not installed" if u.active == "not-found" else f"{u.active} · {u.sub}"
    if u.user:
        detail += " · user"
    return _Row(u.active, u.label, detail)


def _app_row(a: AppStatus) -> _Row:
    if a.running:
        return _Row("running", a.name, f"pid {a.pid} · {a.cpu:.0f}% · {fmt_bytes(a.rss)}")
    return _Row("stopped", a.name, "not running")


class ServicesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._summary = QLabel("Loading…")
        self._summary.setStyleSheet(f"color: {config.TEXT}; font-size: 14px;")
        root.addWidget(self._summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {config.BG}; }}"
            f"QScrollBar:vertical {{ background: {config.BG}; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {config.CARD_ALT}; border-radius: 3px; }}"
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

    def update_snapshot(self, snap: ServicesSnapshot):
        watched_ok = sum(1 for u in snap.watched if u.active == "active")
        apps_ok = sum(1 for a in snap.apps if a.running)
        self._summary.setText(
            f"Apps {apps_ok}/{len(snap.apps)}   ·   "
            f"Key services {watched_ok}/{len(snap.watched)}   ·   "
            f"{len(snap.other_running) + watched_ok} running   ·   "
            f"<span style='color:{config.BAD if snap.failed else config.TEXT_SEC}'>"
            f"{len(snap.failed)} failed</span>"
        )

        while (item := self._list_lay.takeAt(0)) is not None:
            if item.widget():
                item.widget().deleteLater()

        add = self._list_lay.addWidget
        add(_section_header("Apps"))
        for a in snap.apps:
            add(_app_row(a))
        add(_section_header("Key services"))
        for u in snap.watched:
            add(_unit_row(u))
        if snap.failed:
            add(_section_header("Failed units"))
            for u in snap.failed:
                add(_unit_row(u))
        add(_section_header(f"Other running services ({len(snap.other_running)})"))
        for u in snap.other_running:
            add(_unit_row(u))
        self._list_lay.addStretch(1)
