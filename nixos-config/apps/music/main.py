import sys
from PyQt6.QtCore    import QMetaObject, Qt, Q_ARG, pyqtSlot
from PyQt6.QtWidgets import QApplication, QMainWindow

from metadata import MetadataReader, TrackInfo
from ui       import PlayerWidget


class MusicApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music")
        self.setMinimumSize(800, 400)

        self._player = PlayerWidget()
        self._player.control_pressed.connect(self._on_control)
        self.setCentralWidget(self._player)

        # Start metadata reader — posts updates back to this thread via Qt
        self._reader = MetadataReader(self._post_update)
        self._reader.start()

    # Called from the background thread — must not touch Qt directly
    def _post_update(self, info: TrackInfo):
        QMetaObject.invokeMethod(
            self, "_apply_update",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG("PyQt_PyObject", info),
        )

    @pyqtSlot("PyQt_PyObject")
    def _apply_update(self, info: TrackInfo):
        self._player.update_track(info)

    def _on_control(self, action: str):
        # TODO: wire up to MPRIS or shairport-sync control socket
        print(f"[control] {action}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Music")
    window = MusicApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
