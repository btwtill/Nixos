"""On-screen keyboard service (generic placeholder until the design lands).

    osk daemon               run the keyboard, hidden until asked
                             (started by Qtile's autostart)
    osk show | hide | toggle control the running keyboard; `show` and `toggle`
                             start the daemon first if it isn't running

The keyboard is an unmanaged, always-on-top window that never takes focus, so
the text field you tapped keeps it. Keys are sent with xdotool, i.e. they
arrive exactly like real key presses in whatever window is focused.
"""
import subprocess
import sys
import time

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

SERVER_NAME = "homy-osk"
KB_HEIGHT   = 250

BG       = "#1E1E1E"
KEY      = "#333333"
KEY_ALT  = "#2A2A2A"
TEXT     = "#EAEAEA"
ACCENT   = "#3DAEE9"

# Special keys: label -> action
SHIFT, BACK, ENTER, SPACE, HIDE, SYMBOLS, LETTERS = "⇧", "⌫", "⏎", "space", "▾", "123", "ABC"

LETTER_ROWS = [
    list("qwertzuiopü"),
    list("asdfghjklöä"),
    [SHIFT] + list("yxcvbnm") + [BACK],
    [SYMBOLS, ",", SPACE, ".", ENTER, HIDE],
]
SYMBOL_ROWS = [
    list("1234567890"),
    list("@#$%&*-+=_"),
    list("!?/\\:;'\"()") + [BACK],
    [LETTERS, "<", SPACE, ">", ENTER, HIDE],
]

# Relative key widths (default 1)
WIDTHS = {SPACE: 5, SHIFT: 1.5, BACK: 1.5, ENTER: 1.5, SYMBOLS: 1.5, LETTERS: 1.5}


def _xdotool(*args: str):
    subprocess.Popen(["xdotool", *args])


class Keyboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint   # not managed by Qtile
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("kb")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#kb {{ background: {BG}; border-top: 1px solid {KEY}; }}"
            f"QPushButton {{ background: {KEY}; color: {TEXT}; border: none; border-radius: 8px;"
            f" font-size: 20px; }}"
            f"QPushButton[special=\"true\"] {{ background: {KEY_ALT}; font-size: 16px; }}"
            f"QPushButton:pressed, QPushButton:checked {{ background: {ACCENT}; color: {BG}; }}"
        )
        self._shift = False
        self._symbols = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._build()

        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen.x(), screen.bottom() - KB_HEIGHT + 1, screen.width(), KB_HEIGHT)

    def _build(self):
        while (item := self._layout.takeAt(0)) is not None:
            if item.layout():
                while (k := item.layout().takeAt(0)) is not None:
                    if k.widget():
                        k.widget().deleteLater()
        for keys in (SYMBOL_ROWS if self._symbols else LETTER_ROWS):
            row = QHBoxLayout()
            row.setSpacing(6)
            for key in keys:
                row.addWidget(self._key(key), int(WIDTHS.get(key, 1) * 10))
            self._layout.addLayout(row)

    def _key(self, key: str) -> QPushButton:
        special = len(key) > 1 or key in (SHIFT, BACK, ENTER, HIDE)
        label = key.upper() if (self._shift and not special) else key
        btn = QPushButton("" if key == SPACE else label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setMinimumHeight(48)
        btn.setProperty("special", special)
        if key == SHIFT:
            btn.setCheckable(True)
            btn.setChecked(self._shift)
        btn.clicked.connect(lambda: self._press(key))
        return btn

    def _press(self, key: str):
        if key == SHIFT:
            self._shift = not self._shift
            self._build()
        elif key == SYMBOLS or key == LETTERS:
            self._symbols = key == SYMBOLS
            self._build()
        elif key == HIDE:
            self.hide()
        elif key == BACK:
            _xdotool("key", "--clearmodifiers", "BackSpace")
        elif key == ENTER:
            _xdotool("key", "--clearmodifiers", "Return")
        elif key == SPACE:
            _xdotool("key", "--clearmodifiers", "space")
        else:
            char = key.upper() if self._shift else key
            _xdotool("type", "--clearmodifiers", "--", char)
            if self._shift:              # one-shot shift, like phone keyboards
                self._shift = False
                self._build()

    def handle(self, command: str):
        if command == "show" or (command == "toggle" and not self.isVisible()):
            self.show()
            self.raise_()
        elif command in ("hide", "toggle"):
            self.hide()


def run_daemon():
    app = QApplication(sys.argv[:1])
    app.setApplicationName("osk")
    app.setQuitOnLastWindowClosed(False)
    kb = Keyboard()

    QLocalServer.removeServer(SERVER_NAME)    # stale socket from a crash
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        print(f"[osk] cannot listen: {server.errorString()}", file=sys.stderr)
        sys.exit(1)

    def on_connection():
        sock = server.nextPendingConnection()
        def read():
            for line in bytes(sock.readAll()).decode().split():
                kb.handle(line.strip())
            sock.disconnectFromServer()
        sock.readyRead.connect(read)

    server.newConnection.connect(on_connection)
    sys.exit(app.exec())


def send(command: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(f"{command}\n".encode())
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "toggle"
    if cmd == "daemon":
        run_daemon()
        return
    if cmd not in ("show", "hide", "toggle"):
        print(__doc__)
        sys.exit(2)

    QCoreApplication(sys.argv[:1])
    if send(cmd):
        return
    if cmd == "hide":
        return                                  # nothing running, nothing to hide
    subprocess.Popen([sys.executable, __file__, "daemon"], start_new_session=True)
    for _ in range(30):
        time.sleep(0.1)
        if send(cmd):
            return
    print("[osk] keyboard daemon did not start", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
