from PyQt6.QtCore    import Qt, pyqtSignal, QObject
from PyQt6.QtGui     import QPixmap, QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy,
)

from metadata import TrackInfo

# Colours
BG        = "#1a1a2e"
ACCENT    = "#e94560"
TEXT_PRI  = "#eaeaea"
TEXT_SEC  = "#888888"
BTN_BG    = "#16213e"
BTN_HOVER = "#0f3460"


class _Button(QPushButton):
    def __init__(self, symbol: str, parent=None):
        super().__init__(symbol, parent)
        self.setFixedSize(72, 72)
        self.setFont(QFont("monospace", 22))
        self.setStyleSheet(f"""
            QPushButton {{
                background: {BTN_BG};
                color: {TEXT_PRI};
                border: none;
                border-radius: 36px;
            }}
            QPushButton:hover {{
                background: {BTN_HOVER};
            }}
            QPushButton:pressed {{
                background: {ACCENT};
            }}
        """)


class PlayerWidget(QWidget):
    """Main music player UI — displays now-playing info and basic controls."""

    # Emitted when the user presses a control button.
    # Values: "prev", "play_pause", "next", "volume_down", "volume_up"
    control_pressed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._apply_idle()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_track(self, info: TrackInfo):
        self._title.setText(info.title  or "Nothing playing")
        self._artist.setText(info.artist or "")
        self._album.setText(info.album  or "")

        if info.art:
            pix = QPixmap()
            pix.loadFromData(info.art)
            self._art.setPixmap(
                pix.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._art.setPixmap(QPixmap())
            self._art.setText("♪")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(f"background: {BG};")

        root = QHBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(40)

        # --- Album art ---
        self._art = QLabel("♪")
        self._art.setFixedSize(280, 280)
        self._art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._art.setStyleSheet(f"""
            background: {BTN_BG};
            border-radius: 16px;
            color: {TEXT_SEC};
            font-size: 80px;
        """)
        root.addWidget(self._art, 0)

        # --- Right panel ---
        right = QVBoxLayout()
        right.setSpacing(12)
        root.addLayout(right, 1)

        # Track info
        self._title = QLabel("Nothing playing")
        self._title.setFont(QFont("sans-serif", 22, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {TEXT_PRI};")
        self._title.setWordWrap(True)

        self._artist = QLabel("")
        self._artist.setFont(QFont("sans-serif", 16))
        self._artist.setStyleSheet(f"color: {ACCENT};")

        self._album = QLabel("")
        self._album.setFont(QFont("sans-serif", 14))
        self._album.setStyleSheet(f"color: {TEXT_SEC};")

        right.addStretch()
        right.addWidget(self._title)
        right.addWidget(self._artist)
        right.addWidget(self._album)
        right.addStretch()

        # AirPlay hint
        hint = QLabel("Stream via AirPlay to connect")
        hint.setFont(QFont("sans-serif", 11))
        hint.setStyleSheet(f"color: {TEXT_SEC};")
        right.addWidget(hint)
        self._hint = hint

        right.addSpacing(16)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(16)

        self._btn_prev  = _Button("⏮")
        self._btn_play  = _Button("⏸")
        self._btn_next  = _Button("⏭")
        self._btn_vol_d = _Button("🔉")
        self._btn_vol_u = _Button("🔊")

        self._btn_prev.clicked.connect(lambda: self.control_pressed.emit("prev"))
        self._btn_play.clicked.connect(lambda: self.control_pressed.emit("play_pause"))
        self._btn_next.clicked.connect(lambda: self.control_pressed.emit("next"))
        self._btn_vol_d.clicked.connect(lambda: self.control_pressed.emit("volume_down"))
        self._btn_vol_u.clicked.connect(lambda: self.control_pressed.emit("volume_up"))

        for btn in (self._btn_vol_d, self._btn_prev, self._btn_play,
                    self._btn_next, self._btn_vol_u):
            controls.addWidget(btn)

        right.addLayout(controls)
        right.addStretch()

    def _apply_idle(self):
        self._title.setText("Nothing playing")
        self._artist.setText("")
        self._album.setText("")
        self._art.setPixmap(QPixmap())
        self._art.setText("♪")
        self._hint.setVisible(True)

    def _apply_playing(self):
        self._hint.setVisible(False)
