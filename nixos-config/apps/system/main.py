import sys
import threading
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

import collectors
import config
from widgets.resources_page import ResourcesPage
from widgets.services_page  import ServicesPage

# Canvas dimensions (px) — same as the home and lights apps
W, H = 814, 490


class SystemWidget(QWidget):
    """Header with page tabs + stacked Services / Resources pages."""

    _services_polled  = pyqtSignal(object)   # ServicesSnapshot
    _resources_polled = pyqtSignal(object)   # ResourceSnapshot

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(W, H)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {config.BG}; }} QLabel {{ color: {config.TEXT}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── Header: tab buttons (placeholder) + host label ────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)
        self._tabs = QButtonGroup(self)
        for i, name in enumerate(("Services", "Resources")):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedSize(130, 36)
            btn.setStyleSheet(
                f"QPushButton {{ background: {config.CARD}; color: {config.TEXT_SEC};"
                f" border: none; border-radius: 18px; font-size: 14px; }}"
                f"QPushButton:checked {{ background: {config.ACCENT}; color: {config.BG};"
                f" font-weight: bold; }}"
            )
            self._tabs.addButton(btn, i)
            header.addWidget(btn)
        header.addStretch(1)
        host = QLabel(config.HOST_LABEL)
        host.setStyleSheet(f"color: {config.TEXT_SEC}; font-size: 13px;")
        header.addWidget(host)
        root.addLayout(header)

        # ── Pages ─────────────────────────────────────────────────────────────
        self._services  = ServicesPage()
        self._resources = ResourcesPage()
        self._stack = QStackedWidget()
        self._stack.addWidget(self._services)
        self._stack.addWidget(self._resources)
        root.addWidget(self._stack, 1)

        self._tabs.idClicked.connect(self._stack.setCurrentIndex)
        self._tabs.button(0).setChecked(True)

        # ── Background polling ────────────────────────────────────────────────
        self._services_polled.connect(self._services.update_snapshot)
        self._resources_polled.connect(self._resources.update_snapshot)
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        """Runs off the Qt thread; results are delivered via queued signals."""
        scanner = collectors.ProcessScanner()
        sampler = collectors.ResourceSampler()
        apps: list[collectors.AppStatus] = []
        next_services = 0.0
        while True:
            try:
                apps, top = scanner.scan(config.APPS, config.TOP_PROCESSES)
                self._resources_polled.emit(sampler.sample(top))
            except Exception as e:
                print(f"[system-app] resource poll failed: {e}", flush=True)

            if time.monotonic() >= next_services:
                next_services = time.monotonic() + config.SERVICE_POLL_S
                try:
                    snap = collectors.collect_services(config.SERVICES)
                    snap.apps = apps
                    self._services_polled.emit(snap)
                except Exception as e:
                    print(f"[system-app] service poll failed: {e}", flush=True)

            time.sleep(config.RESOURCE_POLL_S)


class SystemApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setCentralWidget(SystemWidget())
        self.setFixedSize(W, H)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("System")
    window = SystemApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
