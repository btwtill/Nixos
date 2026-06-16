from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QSlider,
)

from .image_button import ImageButton


class MusicControls(QWidget):
    """Bottom-left music strip: album cover | transport buttons | seek bar.

    Signals
    -------
    control_pressed(str)   "prev" | "play_pause" | "next"
    seek_changed(float)    0.0 – 1.0 when the user moves the seek bar
    """

    control_pressed = pyqtSignal(str)
    seek_changed    = pyqtSignal(float)

    def __init__(self, assets: Path, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._assets = assets
        self._build_ui()

    # ── public ────────────────────────────────────────────────────────────────

    def update_cover(self, art_bytes: bytes | None):
        if art_bytes:
            pix = QPixmap()
            pix.loadFromData(art_bytes)
            self._cover.setPixmap(
                pix.scaled(160, 160,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            )
            self._cover.setText("")
        else:
            self._cover.setPixmap(QPixmap())
            self._cover.setText("♪")

    def set_playing(self, playing: bool):
        self._btn_play.setChecked(playing)

    def set_progress(self, t: float):
        """Set seek bar position (0.0–1.0) without emitting seek_changed."""
        self._seek.blockSignals(True)
        self._seek.setValue(int(t * 1000))
        self._seek.blockSignals(False)

    # ── internal ──────────────────────────────────────────────────────────────

    def _btn(self, default_file: str, active_file: str,
              label: str, size=(60, 60)) -> ImageButton:
        music = self._assets / "music"
        return ImageButton(
            default_image=str(music / default_file),
            active_image =str(music / active_file),
            size=size, label=label,
        )

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(24)

        # ── Album art ─────────────────────────────────────────────────────────
        self._cover = QLabel("♪")
        self._cover.setFixedSize(160, 160)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet(
            "background: #1A1A1A;"
            "border-radius: 12px;"
            "color: #555555;"
            "font-size: 48px;"
        )
        root.addWidget(self._cover, 0)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(0)
        root.addLayout(right, 1)

        right.addStretch(1)

        # Transport row
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addStretch(1)

        self._btn_prev = self._btn("prev_default.png", "prev_pressed.png", "⏮")
        self._btn_play = self._btn("play_default.png", "play_pressed.png", "▶")
        self._btn_play.setCheckable(True)   # checked = currently playing
        self._btn_next = self._btn("next_default.png", "next_pressed.png", "⏭")

        self._btn_prev.clicked.connect(lambda: self.control_pressed.emit("prev"))
        self._btn_play.clicked.connect(lambda: self.control_pressed.emit("play_pause"))
        self._btn_next.clicked.connect(lambda: self.control_pressed.emit("next"))

        for b in (self._btn_prev, self._btn_play, self._btn_next):
            row.addWidget(b)
        row.addStretch(1)
        right.addLayout(row)

        right.addSpacing(16)

        # Seek bar — basic styled QSlider; will be replaced with custom widget
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 1000)
        self._seek.setValue(0)
        self._seek.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #333333;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #888888;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                background: #CCCCCC;
                border-radius: 7px;
                margin: -5px 0;
            }
        """)
        self._seek.valueChanged.connect(lambda v: self.seek_changed.emit(v / 1000.0))
        right.addWidget(self._seek)

        right.addStretch(1)
