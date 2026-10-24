"""Example launcher app — copy this folder as a starting point for your own.

Install it without rebuilding:   homy-apps install <this folder>
"""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow

W, H = 814, 490   # same canvas as the built-in apps


class HelloApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hello")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        label = QLabel("Hello from an installed app!\n\nGo back with the menu button at the top.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: #1E1E1E; color: #EAEAEA; font-size: 18px;")
        self.setCentralWidget(label)
        self.setFixedSize(W, H)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HelloApp()
    window.show()
    sys.exit(app.exec())
