import subprocess
import sys
import threading
from pathlib import Path

# Shared modules live in apps/common (copied next to this file by default.nix).
sys.path.append(str(Path(__file__).resolve().parent.parent / "common"))

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow

import nm
import ui_kit
from ui_kit import Row, button

REFRESH_MS = 5000


def _osk(command: str):
    """Show/hide the on-screen keyboard service (no-op if it isn't installed)."""
    try:
        subprocess.Popen(["osk", command])
    except OSError:
        pass


def _bars(signal: int) -> str:
    """Placeholder signal-strength glyph."""
    level = 4 if signal >= 75 else 3 if signal >= 50 else 2 if signal >= 25 else 1
    return "▂▄▆█"[:level]


class PasswordEdit(QLineEdit):
    """Password field that brings up the on-screen keyboard when tapped."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        _osk("show")


class PasswordPanel(QFrame):
    submitted = pyqtSignal(str, str)   # ssid, password
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pw")
        self.setStyleSheet(
            f"#pw {{ background: {ui_kit.CARD}; border-radius: 10px; }}"
            f"QLineEdit {{ background: {ui_kit.BG}; color: {ui_kit.TEXT}; border: 1px solid {ui_kit.CARD_ALT};"
            f" border-radius: 8px; padding: 6px 10px; font-size: 16px; }}"
            f"QLineEdit:focus {{ border-color: {ui_kit.ACCENT}; }}"
        )
        self._ssid = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._label = QLabel("")
        self._label.setStyleSheet(f"color: {ui_kit.TEXT}; font-size: 14px;")
        self._edit = PasswordEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("Password")
        self._edit.setFixedHeight(38)
        self._edit.returnPressed.connect(self._submit)
        self._show = button("Show")
        self._show.setCheckable(True)
        self._show.toggled.connect(lambda on: self._edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        ok = button("Join", primary=True)
        ok.clicked.connect(self._submit)
        cancel = button("Cancel")
        cancel.clicked.connect(self._cancel)
        lay.addWidget(self._label)
        lay.addWidget(self._edit, 1)
        lay.addWidget(self._show)
        lay.addWidget(ok)
        lay.addWidget(cancel)
        self.hide()

    def ask(self, ssid: str):
        self._ssid = ssid
        self._label.setText(ssid)
        self._edit.clear()
        self._show.setChecked(False)
        self.show()
        self._edit.setFocus()            # focusInEvent shows the keyboard

    def _submit(self):
        if not self._edit.text():
            return
        self.hide()
        _osk("hide")
        self.submitted.emit(self._ssid, self._edit.text())

    def _cancel(self):
        self.hide()
        _osk("hide")
        self.cancelled.emit()


class WifiPage(ui_kit.Page):
    _state = pyqtSignal(object)                  # nm.WifiState
    _action_done = pyqtSignal(str, bool, str)    # key, ok, message

    def __init__(self, parent=None):
        super().__init__("Wi-Fi", parent)
        self._st: nm.WifiState | None = None
        self._busy: dict[str, str] = {}          # ssid / "__radio__" / "__scan__" -> label
        self._message = ""
        self._last_view: tuple | None = None

        self._radio_btn = button("On")
        self._radio_btn.setCheckable(True)
        self._radio_btn.clicked.connect(self._toggle_radio)
        self._scan_btn = button("Refresh", primary=True)
        self._scan_btn.clicked.connect(self._rescan)
        self.add_action(self._radio_btn)
        self.add_action(self._scan_btn)

        # Password prompt sits above the list, clear of the keyboard at the bottom.
        self._pw = PasswordPanel()
        self._pw.submitted.connect(lambda ssid, pw: self._run(ssid, "Connecting…", nm.connect_new, ssid, pw))
        self.layout().insertWidget(2, self._pw)

        self._state.connect(self._apply_state)
        self._action_done.connect(self._on_action_done)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # ── data ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        threading.Thread(target=lambda: self._state.emit(nm.state()), daemon=True).start()

    def _apply_state(self, st: nm.WifiState):
        self._st = st
        self._render()

    def _run(self, key: str, label: str, fn, *args):
        self._busy[key] = label
        self._render()

        def work():
            ok, msg = fn(*args)
            self._action_done.emit(key, ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def _on_action_done(self, key: str, ok: bool, msg: str):
        label = self._busy.pop(key, "").rstrip("…")
        self._message = "" if ok else (f"{label} failed: {msg}" if msg else f"{label} failed")
        self._refresh()

    # ── actions ───────────────────────────────────────────────────────────────

    def _toggle_radio(self):
        self._run("__radio__", "Switching…", nm.set_radio, self._radio_btn.isChecked())

    def _rescan(self):
        self._run("__scan__", "Scanning…", nm.rescan)

    def _connect(self, net: nm.Network):
        if net.saved_as:
            self._run(net.ssid, "Connecting…", nm.connect_saved, net.saved_as)
        elif net.secure:
            self._pw.ask(net.ssid)
        else:
            self._run(net.ssid, "Connecting…", nm.connect_new, net.ssid, None)

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        st = self._st
        if st is None:
            return
        # Signal is bucketed so small fluctuations don't rebuild (and eat taps).
        nets = tuple((n.ssid, len(_bars(n.signal)), n.security, n.in_use, n.saved_as) for n in st.networks)
        view = (st.device, st.radio_on, st.ip, nets, tuple(sorted(self._busy.items())), self._message)
        if view == self._last_view:
            return
        self._last_view = view

        self._radio_btn.setChecked(st.radio_on)
        self._radio_btn.setText("On" if st.radio_on else "Off")
        self._radio_btn.setEnabled(st.device is not None and "__radio__" not in self._busy)
        self._scan_btn.setEnabled(st.radio_on and "__scan__" not in self._busy)
        self._scan_btn.setText("Scanning…" if "__scan__" in self._busy else "Refresh")

        current = next((n for n in st.networks if n.in_use), None)
        if self._message:
            self.set_status(self._message)
        elif current:
            self.set_status(f"Connected to {current.ssid}" + (f" · {st.ip}" if st.ip else ""))
        else:
            self.set_status("Not connected")

        self.clear_list()
        if st.device is None:
            self.add_note("No Wi-Fi adapter found.")
            self.finish_list()
            return
        if not st.radio_on:
            self.add_note("Wi-Fi is off.")
            self.finish_list()
            return

        if current:
            self.add_section("Current network")
            row = self._row(current, highlight=True)
            b = row.add_button(button("Disconnect"))
            b.setEnabled(current.ssid not in self._busy)
            b.clicked.connect(lambda: self._run(current.ssid, "Disconnecting…", nm.disconnect, st.device))
            if current.saved_as:
                self._forget_btn(row, current)

        others = [n for n in st.networks if not n.in_use]
        self.add_section("Networks")
        if not others:
            self.add_note("No other networks found. Tap Refresh to scan again.")
        for net in others:
            row = self._row(net)
            b = row.add_button(button("Connect", primary=True))
            b.setEnabled(net.ssid not in self._busy)
            b.clicked.connect(lambda _=False, n=net: self._connect(n))
            if net.saved_as:
                self._forget_btn(row, net)
        self.finish_list()

    def _row(self, net: nm.Network, highlight: bool = False) -> Row:
        sub = self._busy.get(net.ssid) or " · ".join(filter(None, [
            "Saved" if net.saved_as else "",
            net.security if net.secure else "Open",
            f"{net.signal}%",
        ]))
        row = Row(_bars(net.signal), net.ssid, sub, highlight=highlight)
        self.add_row(row)
        return row

    def _forget_btn(self, row: Row, net: nm.Network):
        b = row.add_button(button("Forget", danger=True))
        b.setEnabled(net.ssid not in self._busy)
        b.clicked.connect(lambda: self._run(net.ssid, "Forgetting…", nm.forget, net.saved_as))


class WifiApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wi-Fi")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setCentralWidget(WifiPage())
        self.setFixedSize(ui_kit.W, ui_kit.H)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Wi-Fi")
    window = WifiApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
