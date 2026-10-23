import sys
import threading
from pathlib import Path

# Shared modules live in apps/common (copied next to this file by default.nix).
sys.path.append(str(Path(__file__).resolve().parent.parent / "common"))

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow

import bluez
import ui_kit
from ui_kit import Row, button

REFRESH_MS = 2000
SCAN_S     = 30


def _glyph(icon: str) -> str:
    """Placeholder icon per BlueZ device class."""
    if icon.startswith("audio"):
        return "♫"
    if icon.startswith("phone"):
        return "☎"
    if icon.startswith("input"):
        return "⌨"
    return "●"


class BluetoothPage(ui_kit.Page):
    _snapshot = pyqtSignal(object, object)   # Adapter | None, list[Device]
    _action_done = pyqtSignal(str, bool, str)  # address, ok, message

    def __init__(self, parent=None):
        super().__init__("Bluetooth", parent)
        self._adapter: bluez.Adapter | None = None
        self._devices: list[bluez.Device] = []
        self._busy: dict[str, str] = {}        # address -> "Pairing…" etc.
        self._scanning = False
        self._message = ""
        self._last_view: tuple | None = None

        self._power_btn = button("On")
        self._power_btn.setCheckable(True)
        self._power_btn.clicked.connect(self._toggle_power)
        self._scan_btn = button("Scan", primary=True)
        self._scan_btn.clicked.connect(self._start_scan)
        self.add_action(self._power_btn)
        self.add_action(self._scan_btn)

        self._snapshot.connect(self._apply_snapshot)
        self._action_done.connect(self._on_action_done)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # ── data ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        threading.Thread(target=lambda: self._snapshot.emit(*bluez.snapshot()), daemon=True).start()

    def _apply_snapshot(self, adapter, devices):
        self._adapter, self._devices = adapter, devices
        self._render()

    def _run_action(self, address: str, label: str, fn, *args):
        """Run a blocking bluez action in the background, marking the device busy."""
        self._busy[address] = label
        self._render()

        def work():
            ok, msg = fn(*args)
            self._action_done.emit(address, ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def _on_action_done(self, address: str, ok: bool, msg: str):
        label = self._busy.pop(address, "")
        if address == "__scan__":
            self._scanning = False
        elif not ok:
            self._message = f"{label.rstrip('…')} failed: {msg}" if msg else f"{label.rstrip('…')} failed"
        else:
            self._message = ""
        self._refresh()

    # ── header actions ────────────────────────────────────────────────────────

    def _toggle_power(self):
        on = self._power_btn.isChecked()
        self._run_action("__power__", "Switching…", bluez.set_power, on)

    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._run_action("__scan__", "Scanning…", bluez.scan, SCAN_S)

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        # RSSI is left out on purpose: it changes every second while Home
        # Assistant scans, and rebuilding the rows that often would eat taps.
        devices = tuple((d.address, d.name, d.paired, d.connected, d.icon) for d in self._devices)
        view = (self._adapter, devices, tuple(sorted(self._busy.items())),
                self._scanning, self._message)
        if view == self._last_view:
            return                      # nothing changed — keep rows and scroll position
        self._last_view = view

        a = self._adapter
        powered = bool(a and a.powered)
        self._power_btn.setChecked(powered)
        self._power_btn.setText("On" if powered else "Off")
        self._power_btn.setEnabled(a is not None and "__power__" not in self._busy)
        self._scan_btn.setEnabled(powered and not self._scanning)
        self._scan_btn.setText("Scanning…" if self._scanning else "Scan")

        status = self._message or (
            "Scanning — put your device in pairing mode" if self._scanning else
            f"{a.name}" if a else "")
        self.set_status(status)

        self.clear_list()
        if a is None:
            self.add_note("No Bluetooth adapter found.")
            self.finish_list()
            return
        if not powered:
            self.add_note("Bluetooth is off.")
            self.finish_list()
            return

        named = [d for d in self._devices if d.name]
        connected = [d for d in named if d.connected]
        paired = [d for d in named if d.paired and not d.connected]
        available = sorted((d for d in named if not d.paired and not d.connected),
                           key=lambda d: d.rssi if d.rssi is not None else -999, reverse=True)

        if connected:
            self.add_section("Connected")
            for d in connected:
                row = self._row(d, "Connected", highlight=True)
                self._add_btn(row, d, "Disconnect", "Disconnecting…", bluez.disconnect)
        self.add_section("My devices")
        if not paired and not connected:
            self.add_note("No paired devices yet.")
        for d in paired:
            row = self._row(d, "Not connected")
            self._add_btn(row, d, "Connect", "Connecting…", bluez.connect, primary=True)
            self._add_btn(row, d, "Forget", "Removing…", bluez.forget, danger=True)
        self.add_section("Available devices")
        if not available:
            self.add_note("Tap Scan and put your device in pairing mode." if not self._scanning
                          else "Searching…")
        for d in available:
            sub = d.address + (f" · {d.rssi} dBm" if d.rssi is not None else "")
            row = self._row(d, sub)
            self._add_btn(row, d, "Pair", "Pairing…", bluez.pair_and_connect, primary=True)
        self.finish_list()

    def _row(self, d: bluez.Device, subtitle: str, highlight: bool = False) -> Row:
        if d.address in self._busy:
            subtitle = self._busy[d.address]
        row = Row(_glyph(d.icon), d.name, subtitle, highlight=highlight)
        self.add_row(row)
        return row

    def _add_btn(self, row: Row, d: bluez.Device, text: str, busy_label: str, fn,
                 primary: bool = False, danger: bool = False):
        btn = row.add_button(button(text, primary=primary, danger=danger))
        btn.setEnabled(d.address not in self._busy)
        btn.clicked.connect(lambda: self._run_action(d.address, busy_label, fn, d.address))


class BluetoothApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bluetooth")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setCentralWidget(BluetoothPage())
        self.setFixedSize(ui_kit.W, ui_kit.H)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bluetooth")
    window = BluetoothApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
