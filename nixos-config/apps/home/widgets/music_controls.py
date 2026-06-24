from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel,
)

from .image_button import ImageButton
from .linear_slider import LinearSlider


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
        self._music  = assets / "music"
        self._cover_placeholder = QPixmap(str(self._music / "MusicCover.png"))
        self._build_ui()

    # ── public ────────────────────────────────────────────────────────────────

    def update_cover(self, art_bytes: bytes | None):
        if art_bytes:
            pix = QPixmap()
            pix.loadFromData(art_bytes)
        else:
            pix = self._cover_placeholder
        self._cover.setPixmap(
            pix.scaled(180, 180,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        )

    def set_playing(self, playing: bool):
        self._btn_play.setChecked(playing)

    def set_progress(self, t: float):
        """Set seek bar position (0.0–1.0) without emitting seek_changed."""
        self._seek.set_value_silent(t)

    # ── internal ──────────────────────────────────────────────────────────────

    def _btn(self, default_file: str, active_file: str,
              label: str, size=(80, 80)) -> ImageButton:
        return ImageButton(
            default_image=str(self._music / default_file),
            active_image =str(self._music / active_file),
            size=size, label=label,
        )

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(24)

        # ── Album art ─────────────────────────────────────────────────────────
        self._cover = QLabel()
        self._cover.setFixedSize(180, 180)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet("background: transparent;")
        self._cover.setPixmap(
            self._cover_placeholder.scaled(
                180, 180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        root.addWidget(self._cover, 0)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(0)
        root.addLayout(right, 1)

        right.addStretch(1)

        # Transport row
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch(1)

        self._btn_prev = self._btn("Backward_Button.png", "Backward_Button_Pushed.png", "⏮")
        self._btn_play = self._btn("Play_Button.png", "Play_Button_Pushed.png", "▶")
        self._btn_play.setCheckable(True)   # checked = currently playing
        self._btn_next = self._btn("Forward_Button.png", "Forward_Button_Pushed.png", "⏭")

        self._btn_prev.clicked.connect(lambda: self.control_pressed.emit("prev"))
        self._btn_play.clicked.connect(lambda: self.control_pressed.emit("play_pause"))
        self._btn_next.clicked.connect(lambda: self.control_pressed.emit("next"))

        for b in (self._btn_prev, self._btn_play, self._btn_next):
            row.addWidget(b)
        row.addStretch(1)
        right.addLayout(row)

        right.addSpacing(16)

        # Seek bar — backdrop + fill artwork (fill cropped to value, not
        # stretched) + knob, all custom-painted by LinearSlider.
        self._seek = LinearSlider(
            bg_image     = str(self._music / "VolumeSliderBackdrop.png"),
            fill_image   = str(self._music / "VolumeSliderAmount.png"),
            handle_image = str(self._music / "SliderKnob.png"),
            track_height = 20,
            handle_size  = (19, 39),
        )
        self._seek.value_changed.connect(self.seek_changed.emit)
        right.addWidget(self._seek)

        right.addStretch(1)
