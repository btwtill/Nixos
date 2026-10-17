"""Page 2 — live CPU, memory, temperature, storage, network and top processes."""
from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import config
from collectors import ResourceSnapshot, fmt_bytes, fmt_uptime
from widgets.placeholders import Bar, Card, StatTile

# Pi 3B+ throttles at 80 °C, hard limit 85 °C.
TEMP_MAX_C = 85.0


class _ProcessCard(Card):
    def __init__(self, parent=None):
        super().__init__("Top processes (CPU)", parent)
        self._rows: list[tuple[QLabel, QLabel, QLabel]] = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        for i in range(config.TOP_PROCESSES):
            name, cpu, mem = QLabel(""), QLabel(""), QLabel("")
            for lbl in (name, cpu, mem):
                lbl.setStyleSheet("font-size: 13px;")
            cpu.setFixedWidth(60)
            mem.setFixedWidth(80)
            grid.addWidget(name, i, 0)
            grid.addWidget(cpu, i, 1)
            grid.addWidget(mem, i, 2)
            self._rows.append((name, cpu, mem))
        self.body.addLayout(grid)
        self.body.addStretch(1)

    def update_procs(self, procs):
        for i, (name, cpu, mem) in enumerate(self._rows):
            if i < len(procs):
                p = procs[i]
                name.setText(f"{p.name}  <span style='color:{config.TEXT_SEC}'>{p.pid}</span>")
                cpu.setText(f"{p.cpu:.1f}%")
                mem.setText(fmt_bytes(p.rss))
            else:
                name.setText(""); cpu.setText(""); mem.setText("")


class _CoresTile(Card):
    """One small bar per core, created lazily once the core count is known."""

    def __init__(self, parent=None):
        super().__init__("Cores", parent)
        self._bars: list[Bar] = []
        self._lay = QVBoxLayout()
        self._lay.setSpacing(6)
        self.body.addLayout(self._lay)
        self.body.addStretch(1)

    def update_cores(self, values: list[float]):
        if len(self._bars) != len(values):
            for i in range(len(values)):
                row = QHBoxLayout()
                lbl = QLabel(f"{i}")
                lbl.setFixedWidth(14)
                lbl.setStyleSheet(f"color: {config.TEXT_SEC}; font-size: 11px;")
                bar = Bar(8)
                row.addWidget(lbl)
                row.addWidget(bar, 1)
                self._lay.addLayout(row)
                self._bars.append(bar)
        for bar, v in zip(self._bars, values):
            bar.set_value(v / 100)


class ResourcesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        self._cpu   = StatTile("CPU", sparkline=True)
        self._mem   = StatTile("Memory", sparkline=True)
        self._temp  = StatTile("Temperature")
        self._disk  = StatTile("Storage /")
        self._net   = StatTile("Network", bar=False)
        self._sys   = StatTile("Load · Uptime", bar=False)
        self._cores = _CoresTile()
        self._procs = _ProcessCard()

        grid.addWidget(self._cpu,   0, 0)
        grid.addWidget(self._mem,   0, 1)
        grid.addWidget(self._temp,  0, 2)
        grid.addWidget(self._cores, 0, 3, 2, 1)
        grid.addWidget(self._disk,  1, 0)
        grid.addWidget(self._net,   1, 1)
        grid.addWidget(self._sys,   1, 2)
        grid.addWidget(self._procs, 2, 0, 1, 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)
        grid.setRowStretch(2, 3)

    def update_snapshot(self, s: ResourceSnapshot):
        self._cpu.value.setText(f"{s.cpu_percent:.0f}%")
        self._cpu.sub.setText(f"{s.cpu_freq_mhz:.0f} MHz" if s.cpu_freq_mhz else f"{len(s.per_core)} cores")
        self._cpu.spark.push(s.cpu_percent / 100)
        self._cpu.bar.set_value(s.cpu_percent / 100)

        mem_frac = s.mem_used / s.mem_total if s.mem_total else 0
        self._mem.value.setText(f"{mem_frac * 100:.0f}%")
        swap = f" · swap {fmt_bytes(s.swap_used)}" if s.swap_total else ""
        self._mem.sub.setText(f"{fmt_bytes(s.mem_used)} / {fmt_bytes(s.mem_total)}{swap}")
        self._mem.spark.push(mem_frac)
        self._mem.bar.set_value(mem_frac)

        if s.temp_c is not None:
            self._temp.value.setText(f"{s.temp_c:.0f} °C")
            self._temp.sub.setText("CPU")
            self._temp.bar.set_value(s.temp_c / TEMP_MAX_C)
        else:
            self._temp.value.setText("n/a")
            self._temp.sub.setText("no sensor")
            self._temp.bar.set_value(0)

        self._cores.update_cores(s.per_core)

        disk_frac = s.disk_used / s.disk_total if s.disk_total else 0
        self._disk.value.setText(f"{disk_frac * 100:.0f}%")
        self._disk.sub.setText(f"{fmt_bytes(s.disk_used)} / {fmt_bytes(s.disk_total)}")
        self._disk.bar.set_value(disk_frac)

        self._net.value.setText(f"↓ {fmt_bytes(s.net_rx_bps)}/s")
        self._net.sub.setText(f"↑ {fmt_bytes(s.net_tx_bps)}/s")

        l1, l5, l15 = s.load_avg
        self._sys.value.setText(f"{l1:.2f}")
        self._sys.sub.setText(f"{l5:.2f} · {l15:.2f}   up {fmt_uptime(s.uptime_s)}")

        self._procs.update_procs(s.top_procs)
