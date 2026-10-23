import sys
from pathlib import Path

# Shared modules live in apps/common (copied next to this file by default.nix).
sys.path.append(str(Path(__file__).resolve().parent.parent / "common"))

from PyQt6.QtCore    import pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow

import airplay
from ui import PlayerWidget


class MusicApp(QMainWindow):
    _track_changed = pyqtSignal(object)   # airplay.TrackInfo, from the watcher thread

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music")
        self.setMinimumSize(800, 400)

        self._player = PlayerWidget()
        self._player.control_pressed.connect(airplay.run_action)
        self.setCentralWidget(self._player)

        self._track_changed.connect(self._player.update_track)
        self._watcher = airplay.AirPlayWatcher(self._track_changed.emit)
        self._watcher.start()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Music")
    window = MusicApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
