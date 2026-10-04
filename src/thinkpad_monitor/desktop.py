"""Native Qt Widgets dashboard for Laptop Monitor (read-only, no tray)."""
from __future__ import annotations
import argparse
import os
import sys
import time
from PySide6 import QtCore, QtGui, QtWidgets

__all__ = ["main", "MonitorWindow", "build_parser", "run_smoke_test"]
DISPLAY_NAME = "Laptop Monitor"
UNAVAILABLE = "Unavailable"
CPU_HISTORY_LIMIT = 180

def fmt_percent(v, d=0):
    if v is None:
        return UNAVAILABLE
    try:
        return ("%." + str(d) + "f%%") % float(v)
    except (TypeError, ValueError):
        return UNAVAILABLE

def fmt_num(v, d=1, s=""):
    if v is None:
        return UNAVAILABLE
    try:
        return ("%." + str(d) + "f") % float(v) + s
    except (TypeError, ValueError):
        return UNAVAILABLE

def fmt_int(v):
    if v is None:
        return UNAVAILABLE
    try:
        return "{:,}".format(int(v))
    except (TypeError, ValueError):
        return UNAVAILABLE

def fmt_bytes(v):
    if v is None:
        return UNAVAILABLE
    try:
        n = float(v)
    except (TypeError, ValueError):
        return UNAVAILABLE
    for u in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024.0 or u == "PiB":
            return "%d B" % int(n) if u == "B" else "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f PiB" % n

def fmt_rate(v):
    return UNAVAILABLE if v is None else fmt_bytes(v) + "/s"

def fmt_duration(s):
    if s is None:
        return UNAVAILABLE
    try:
        t = int(float(s))
    except (TypeError, ValueError):
        return UNAVAILABLE
    if t < 0:
        return UNAVAILABLE
    d, r = divmod(t, 86400)
    h, r = divmod(r, 3600)
    m, sec = divmod(r, 60)
    if d:
        return "%dd %02d:%02d:%02d" % (d, h, m, sec)
    if h:
        return "%02d:%02d:%02d" % (h, m, sec)
    return "%02d:%02d" % (m, sec)

def fmt_celsius(v):
    return fmt_num(v, 1, " \u00b0C")
def fmt_rpm(v):
    return fmt_num(v, 0, " RPM")
def fmt_volts(v):
    return fmt_num(v, 3, " V")
def fmt_watts(v):
    return fmt_num(v, 2, " W")
def fmt_mhz(v):
    return fmt_num(v, 0, " MHz")

def _text(v):
    if v is None:
        return UNAVAILABLE
    if isinstance(v, str):
        s = v.strip()
        return s if s else UNAVAILABLE
    return str(v)

def _as_list(v):
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]

def _section(s, k):
    if isinstance(s, dict):
        v = s.get(k)
        if isinstance(v, dict):
            return v
    return {}


class SampleWorker(QtCore.QObject):
    """Off-thread sampler. Window emits ``request`` (queued); ``_do_sample`` runs on worker thread."""
    sampled = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    finished = QtCore.Signal()
    request = QtCore.Signal()
    def __init__(self, collector, parent=None):
        super().__init__(parent)
        self._collector = collector
        self._busy = False
        self.request.connect(self._do_sample)
    @property
    def busy(self):
        return self._busy
    @QtCore.Slot()
    def _do_sample(self):
        if self._busy:
            return
        self._busy = True
        try:
            data = self._collector.sample()
            if not isinstance(data, dict):
                raise TypeError("collector.sample() must return a dict")
            self.sampled.emit(data)
        except Exception as exc:
            try:
                self.failed.emit(str(exc))
            except Exception:
                pass
        finally:
            self._busy = False
            try:
                self.finished.emit()
            except Exception:
                pass


class SummaryCard(QtWidgets.QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self._title = QtWidgets.QLabel(title)
        f = self._title.font()
        f.setPointSizeF(max(8.0, f.pointSizeF() - 1.0))
        self._title.setFont(f)
        self._title.setWordWrap(True)
        self._value = QtWidgets.QLabel(UNAVAILABLE)
        vf = self._value.font()
        vf.setPointSizeF(vf.pointSizeF() + 3.0)
        vf.setBold(True)
        self._value.setFont(vf)
        self._value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._value.setWordWrap(True)
        self._detail = QtWidgets.QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setVisible(False)
        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._detail)
    def set_value(self, value, detail=None):
        self._value.setText(UNAVAILABLE if value is None else str(value))
        if detail:
            self._detail.setText(str(detail))
            self._detail.setVisible(True)
        else:
            self._detail.setText("")
            self._detail.setVisible(False)
    @property
    def value_text(self):
        return self._value.text()


class UsageBar(QtWidgets.QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self._available = False
    def set_usage(self, percent, text=None):
        if percent is None:
            self._available = False
            self.setValue(0)
            self.setFormat(UNAVAILABLE)
            return
        try:
            v = max(0, min(100, int(round(float(percent)))))
        except (TypeError, ValueError):
            self._available = False
            self.setFormat(UNAVAILABLE)
            return
        self._available = True
        self.setValue(v)
        self.setFormat(text or "%p%")
    @property
    def available(self):
        return self._available


class CpuGraph(QtWidgets.QWidget):
    def __init__(self, parent=None, limit=CPU_HISTORY_LIMIT):
        super().__init__(parent)
        self._samples: list = []
        self._limit = max(2, int(limit))
        self.setMinimumHeight(110)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setAccessibleName("CPU usage history graph")
    def append(self, percent):
        if percent is None:
            return
        try:
            v = float(percent)
        except (TypeError, ValueError):
            return
        self._samples.append(max(0.0, min(100.0, v)))
        if len(self._samples) > self._limit:
            del self._samples[:len(self._samples) - self._limit]
        self.update()
    @property
    def samples(self):
        return list(self._samples)
    def clear(self):
        self._samples = []
        self.update()
    def sizeHint(self):
        return QtCore.QSize(320, 120)
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        try:
            rect = self.rect()
            pal = self.palette()
            p.fillRect(rect, pal.base())
            p.setPen(QtGui.QPen(pal.color(QtGui.QPalette.ColorRole.Mid)))
            for pct in (0, 50, 100):
                y = rect.bottom() - int(rect.height() * (pct / 100.0))
                p.drawLine(rect.left(), y, rect.right(), y)
            f = p.font()
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
            p.setFont(f)
            p.setPen(pal.color(QtGui.QPalette.ColorRole.Text))
            p.drawText(2, rect.top() + 12, "100%")
            p.drawText(2, rect.center().y() + 4, "50%")
            p.drawText(2, rect.bottom() - 2, "0%")
            if not self._samples:
                p.drawText(rect.center().x() - 40, rect.center().y(), "No samples yet")
                return
            pl, pr = 34, max(35, rect.right() - 4)
            pt, pb = rect.top() + 2, rect.bottom() - 2
            span = max(1, pb - pt)
            n = len(self._samples)
            step = (pr - pl) / float(self._limit)
            pts = [QtCore.QPointF(pl + (self._limit - n + i) * step,
                                  pb - int(span * (v / 100.0)))
                   for i, v in enumerate(self._samples)]
            p.setPen(QtGui.QPen(pal.color(QtGui.QPalette.ColorRole.Highlight)))
            path = QtGui.QPainterPath()
            path.moveTo(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            p.drawPath(path)
        finally:
            p.end()


class DetailTable(QtWidgets.QTableWidget):
    def __init__(self, headers, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        h.setStretchLastSection(True)
    def set_rows(self, rows):
        safe = list(rows)
        horizontal, vertical = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(len(safe))
            for r, row in enumerate(safe):
                for c in range(self.columnCount()):
                    t = row[c] if c < len(row) else ""
                    text = UNAVAILABLE if t is None else str(t)
                    item = self.item(r, c)
                    if item is None:
                        item = QtWidgets.QTableWidgetItem(text)
                        self.setItem(r, c, item)
                    elif item.text() != text:
                        item.setText(text)
                    item.setToolTip(text)
            self.horizontalScrollBar().setValue(horizontal)
            self.verticalScrollBar().setValue(vertical)
        finally:
            self.setUpdatesEnabled(True)


class MonitorWindow(QtWidgets.QMainWindow):
    def __init__(self, collector=None, interval=2.0, parent=None):
        super().__init__(parent)
        self._interval = max(0.25, float(interval))
        self._paused = False
        self._last_sample = None
        self._error = None
        self._shutting_down = False
        self._sampling = False
        self._close_pending = False
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(980, 720)
        if collector is None:
            from .telemetry import Collector
            collector = Collector()
        self._collector = collector
        self._build_ui()
        self._build_worker()
        self._apply_interval()
        QtCore.QTimer.singleShot(0, self._tick)
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        hdr = QtWidgets.QHBoxLayout()
        self._title_label = QtWidgets.QLabel(DISPLAY_NAME)
        f = self._title_label.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 2.0)
        self._title_label.setFont(f)
        hdr.addWidget(self._title_label)
        hdr.addStretch(1)
        self._status_label = QtWidgets.QLabel("Starting...")
        hdr.addWidget(self._status_label)
        root.addLayout(hdr)
        hdr = QtWidgets.QHBoxLayout()
        hdr.addStretch(1)
        self._pause_button = QtWidgets.QPushButton("Pause")
        self._pause_button.clicked.connect(self.toggle_pause)
        hdr.addWidget(self._pause_button)
        self._refresh_button = QtWidgets.QPushButton("Refresh")
        self._refresh_button.clicked.connect(self.refresh_now)
        hdr.addWidget(self._refresh_button)
        self._interval_combo = QtWidgets.QComboBox()
        for s in (0.5, 1.0, 2.0, 5.0, 10.0):
            self._interval_combo.addItem("%gs" % s, s)
        self._interval_combo.setCurrentIndex(2)
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        self._interval_combo.setToolTip("Refresh interval")
        hdr.addWidget(self._interval_combo)
        root.addLayout(hdr)
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs, 1)
        self._build_summary_tab()
        self._cpu_table = self._table_tab("CPU", ["Metric", "Value"])
        self._mem_table = self._table_tab("Memory", ["Metric", "Value"])
        self._storage_table = self._table_tab("Storage", ["Metric", "Value"])
        self._battery_table = self._table_tab("Batteries", ["Name", "Status", "Charge", "Health", "Cycles", "Voltage", "Power", "Energy", "Remaining"])
        self._net_table = self._table_tab("Networks", ["Interface", "Up", "Addresses", "RX/s", "TX/s", "RX total", "TX total"])
        lay = self._add_scroll_tab("Thermals and Fans")
        lay.addWidget(QtWidgets.QLabel("Temperatures"))
        self._temp_table = DetailTable(["Sensor", "Label", "Temp", "Critical"])
        lay.addWidget(self._temp_table)
        lay.addWidget(QtWidgets.QLabel("Fans"))
        self._fan_table = DetailTable(["Fan", "Label", "Speed"])
        lay.addWidget(self._fan_table)
        self._gpu_table = self._table_tab("GPUs", ["GPU", "Vendor", "Driver", "Busy", "Temp", "VRAM used", "VRAM total"])
        self._power_table = self._table_tab("Power", ["Domain", "Watts"])
        sys_lay = self._add_scroll_tab("System")
        self._system_table = DetailTable(["Field", "Value"])
        sys_lay.addWidget(self._system_table)
        sys_lay.addWidget(QtWidgets.QLabel("Warnings"))
        self._warnings_label = QtWidgets.QLabel("")
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setAccessibleName("Collection warnings")
        sys_lay.addWidget(self._warnings_label)
        sys_lay.addStretch(1)
    def _add_scroll_tab(self, title):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self._tabs.addTab(scroll, title)
        return lay
    def _table_tab(self, title, headers, extra_graph=False):
        lay = self._add_scroll_tab(title)
        table = DetailTable(headers)
        if extra_graph:
            lay.addWidget(QtWidgets.QLabel("CPU usage history (most recent samples)"))
            self._graph = CpuGraph()
            lay.addWidget(self._graph)
        lay.addWidget(table)
        return table
    def _build_summary_tab(self):
        lay = self._add_scroll_tab("Summary")
        hl = QtWidgets.QLabel("Host")
        f = hl.font()
        f.setBold(True)
        hl.setFont(f)
        lay.addWidget(hl)
        self._host_value = QtWidgets.QLabel(UNAVAILABLE)
        self._host_value.setWordWrap(True)
        self._host_value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._host_value)
        grid = QtWidgets.QGridLayout()
        self._summary_grid = grid
        grid.setSpacing(10)
        lay.addLayout(grid)
        self._cards = {}
        for key, title in (("cpu", "CPU"), ("memory", "Memory"), ("battery", "Battery"), ("storage", "Storage"), ("temp", "Hottest Sensor"), ("net", "Network"), ("gpu", "GPU"), ("fan", "Fan")):
            self._cards[key] = SummaryCard(title)
        for i, key in enumerate(("cpu", "memory", "battery", "storage", "temp", "net", "gpu", "fan")):
            grid.addWidget(self._cards[key], i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        self._cpu_bar = UsageBar()
        lay.addWidget(self._cpu_bar)
        self._mem_bar = UsageBar()
        lay.addWidget(self._mem_bar)
        self._battery_bar = UsageBar()
        lay.addWidget(self._battery_bar)
        lay.addWidget(QtWidgets.QLabel("CPU history · latest 180 samples"))
        self._graph = CpuGraph()
        lay.addWidget(self._graph)
        lay.addStretch(1)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        grid = getattr(self, "_summary_grid", None)
        if grid is None:
            return
        columns = 4 if self.width() >= 850 else 2 if self.width() >= 480 else 1
        for column in range(4):
            grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, key in enumerate(("cpu", "memory", "battery", "storage", "temp", "net", "gpu", "fan")):
            grid.addWidget(self._cards[key], index // columns, index % columns)

    def _build_worker(self):
        self._thread = QtCore.QThread(self)
        self._worker = SampleWorker(self._collector)
        self._worker.moveToThread(self._thread)
        self._worker.sampled.connect(self._on_sample)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._on_sample_done)
        self._thread.finished.connect(self._worker.deleteLater)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._thread.start()
    def _apply_interval(self):
        self._timer.setInterval(int(self._interval * 1000))
        idx = self._interval_combo.findData(self._interval)
        if idx < 0:
            self._interval_combo.addItem("%gs" % self._interval, self._interval)
            idx = self._interval_combo.count() - 1
        if idx >= 0 and idx != self._interval_combo.currentIndex():
            b = self._interval_combo.blockSignals(True)
            self._interval_combo.setCurrentIndex(idx)
            self._interval_combo.blockSignals(b)
    def _on_interval_changed(self, _i):
        data = self._interval_combo.currentData()
        if data is None:
            return
        self._interval = max(0.25, float(data))
        self._apply_interval()
        self._status_label.setText("Interval: %gs" % self._interval)
        if not self._paused:
            self._tick()
    @property
    def interval(self):
        return self._interval
    @property
    def paused(self):
        return self._paused
    @property
    def last_sample(self):
        return self._last_sample
    @property
    def last_error(self):
        return self._error
    @property
    def cpu_history(self):
        return self._graph.samples
    def toggle_pause(self):
        if self._paused:
            self._paused = False
            self._pause_button.setText("Pause")
            self._status_label.setText("Resumed")
            self._tick()
        else:
            self._paused = True
            self._pause_button.setText("Resume")
            self._status_label.setText("Paused")
        return self._paused
    def refresh_now(self):
        self._error = None
        self._request_sample()
    def _request_sample(self):
        if self._shutting_down or self._sampling:
            return
        self._sampling = True
        self._worker.request.emit()
    def _tick(self):
        if self._shutting_down or self._paused:
            return
        self._request_sample()
    def _on_sample_done(self):
        self._sampling = False
        if self._close_pending:
            self.close()
            return
        if not self._paused and not self._shutting_down:
            self._timer.start(int(self._interval * 1000))
    def _on_sample(self, sample):
        self._last_sample = sample
        self._error = None
        self._render(sample)
        self._status_label.setText("Updated")
    def _on_failure(self, message):
        self._error = message
        self._status_label.setText("Collection failed · readings may be stale")
        self._warnings_label.setText("Last collection failed: %s" % message)
    def _render(self, sample):
        system, cpu = _section(sample, "system"), _section(sample, "cpu")
        memory, storage = _section(sample, "memory"), _section(sample, "storage")
        self._host_value.setText("%s \u2014 %s (%s)" % (_text(system.get("hostname")), _text(system.get("model")), _text(system.get("architecture"))))
        bits = [t for t in ((_text(cpu["governor"]) if cpu.get("governor") is not None else UNAVAILABLE), (_text(cpu["driver"]) if cpu.get("driver") is not None else UNAVAILABLE)) if t != UNAVAILABLE]
        self._cards["cpu"].set_value(fmt_percent(cpu.get("percent")), " \u00b7 ".join(bits) if bits else None)
        self._cpu_bar.set_usage(cpu.get("percent"), "CPU · " + fmt_percent(cpu.get("percent")))
        self._cards["memory"].set_value(fmt_percent(memory.get("percent")), "%s / %s" % (fmt_bytes(memory.get("used_bytes")), fmt_bytes(memory.get("total_bytes"))))
        self._mem_bar.set_usage(memory.get("percent"), "Memory · " + fmt_percent(memory.get("percent")))
        self._cards["storage"].set_value(fmt_percent(storage.get("percent")), "%s / %s" % (fmt_bytes(storage.get("used_bytes")), fmt_bytes(storage.get("total_bytes"))))
        bats = [b for b in _as_list(sample.get("batteries")) if isinstance(b, dict)]
        if not bats:
            self._cards["battery"].set_value(UNAVAILABLE, "No battery detected")
            self._battery_bar.set_usage(None)
        else:
            if len(bats) == 1:
                percentage = bats[0].get("percent")
                summary = fmt_percent(percentage)
                detail = _text(bats[0].get("status"))
            else:
                summary = " · ".join("%s %s" % (_text(b.get("name")), fmt_percent(b.get("percent"))) for b in bats)
                detail = "%d batteries · see Batteries tab" % len(bats)
                if all(b.get("energy_wh") is not None and b.get("full_energy_wh") is not None for b in bats):
                    total = sum(b["full_energy_wh"] for b in bats)
                    percentage = 100 * sum(b["energy_wh"] for b in bats) / total if total > 0 else None
                else:
                    percentage = None
            self._cards["battery"].set_value(summary, detail)
            self._battery_bar.set_usage(percentage, "Battery · " + fmt_percent(percentage))
        temps = [t for t in _as_list(sample.get("temperatures")) if isinstance(t, dict)]
        hot, hotv = None, None
        for t in temps:
            try:
                v = float(t["celsius"]) if t.get("celsius") is not None else None
            except (TypeError, ValueError):
                continue
            if v is not None and (hotv is None or v > hotv):
                hot, hotv = t, v
        if hot is None:
            self._cards["temp"].set_value(UNAVAILABLE, "No temperature sensors" if not temps else None)
        else:
            self._cards["temp"].set_value(fmt_celsius(hotv), _text(hot.get("label") or hot.get("name")))
        nets = [n for n in _as_list(sample.get("networks")) if isinstance(n, dict)]
        active = [n for n in nets if n.get("is_up") and n.get("name") != "lo"]
        act = max(active, key=lambda n: (n.get("rx_bytes_per_second") or 0) +
                  (n.get("tx_bytes_per_second") or 0), default=None)
        if act is None:
            self._cards["net"].set_value(UNAVAILABLE, "No active interface" if not nets else None)
        else:
            self._cards["net"].set_value(_text(act.get("name")), "\u2193 %s  \u2191 %s" % (fmt_rate(act.get("rx_bytes_per_second")), fmt_rate(act.get("tx_bytes_per_second"))))
        gpus = [g for g in _as_list(sample.get("gpus")) if isinstance(g, dict)]
        busy = None
        for g in gpus:
            if g.get("busy_percent") is None:
                continue
            try:
                cur = float(g["busy_percent"])
                if busy is None or cur > float(busy.get("busy_percent") or 0):
                    busy = g
            except (TypeError, ValueError):
                continue
        if busy is None:
            detail = "No GPU detected" if not gpus else ", ".join(
                _text(g.get("vendor") or g.get("driver") or g.get("name")) for g in gpus
            ) + " · load unavailable"
            self._cards["gpu"].set_value(UNAVAILABLE, detail)
        else:
            self._cards["gpu"].set_value(fmt_percent(busy.get("busy_percent")), _text(busy.get("name")))
        fans = [f for f in _as_list(sample.get("fans")) if isinstance(f, dict)]
        spd = []
        for f in fans:
            if f.get("rpm") is None:
                continue
            try:
                spd.append(float(f["rpm"]))
            except (TypeError, ValueError):
                continue
        if not spd:
            self._cards["fan"].set_value(UNAVAILABLE, "No fan sensors" if not fans else None)
        else:
            self._cards["fan"].set_value(fmt_rpm(max(spd)), "%d sensor(s)" % len(spd))
        self._graph.append(cpu.get("percent"))
        per_core, freqs, load = _as_list(cpu.get("per_core_percent")), _as_list(cpu.get("frequencies_mhz")), _as_list(cpu.get("load_average"))
        self._cpu_table.set_rows([["Overall", fmt_percent(cpu.get("percent"))], ["Load average (1/5/15m)", ", ".join(fmt_num(x, 2) for x in load) if load else UNAVAILABLE], ["Governor", _text(cpu.get("governor"))], ["Scaling driver", _text(cpu.get("driver"))], ["Per-core load", ", ".join(fmt_percent(x) for x in per_core) if per_core else UNAVAILABLE], ["Frequencies (MHz)", ", ".join(fmt_mhz(x) for x in freqs) if freqs else UNAVAILABLE]])
        self._mem_table.set_rows([["Total", fmt_bytes(memory.get("total_bytes"))], ["Used", fmt_bytes(memory.get("used_bytes"))], ["Available", fmt_bytes(memory.get("available_bytes"))], ["Used %", fmt_percent(memory.get("percent"))], ["Swap total", fmt_bytes(memory.get("swap_total_bytes"))], ["Swap used", fmt_bytes(memory.get("swap_used_bytes"))], ["Swap %", fmt_percent(memory.get("swap_percent"))]])
        self._storage_table.set_rows([["Total", fmt_bytes(storage.get("total_bytes"))], ["Used", fmt_bytes(storage.get("used_bytes"))], ["Used %", fmt_percent(storage.get("percent"))], ["Read rate", fmt_rate(storage.get("read_bytes_per_second"))], ["Write rate", fmt_rate(storage.get("write_bytes_per_second"))]])
        rows = [[_text(e.get("name")), _text(e.get("status")), fmt_percent(e.get("percent")), fmt_percent(e.get("health_percent")), fmt_int(e.get("cycles")), fmt_volts(e.get("voltage_volts")), fmt_watts(e.get("power_watts")), "%s / %s" % (fmt_num(e.get("energy_wh"), 1), fmt_num(e.get("full_energy_wh"), 1)), fmt_duration(e.get("time_remaining_seconds"))] for e in bats]
        self._battery_table.set_rows(rows or [["No batteries detected"] + [""] * 8])
        nrows = []
        for e in nets:
            addrs = _as_list(e.get("addresses"))
            up = e.get("is_up")
            nrows.append([_text(e.get("name")), "Yes" if up else ("No" if up is not None else UNAVAILABLE), ", ".join(_text(a) for a in addrs) if addrs else UNAVAILABLE, fmt_rate(e.get("rx_bytes_per_second")), fmt_rate(e.get("tx_bytes_per_second")), fmt_bytes(e.get("received_bytes")), fmt_bytes(e.get("sent_bytes"))])
        self._net_table.set_rows(nrows or [["No network interfaces"] + [""] * 6])
        self._temp_table.set_rows([[_text(t.get("name")), _text(t.get("label")), fmt_celsius(t.get("celsius")), fmt_celsius(t.get("critical_celsius"))] for t in temps] or [["No temperature sensors"] + [""] * 3])
        self._fan_table.set_rows([[_text(f.get("name")), _text(f.get("label")), fmt_rpm(f.get("rpm"))] for f in fans] or [["No fan sensors"] + [""] * 2])
        self._gpu_table.set_rows([[_text(g.get("name")), _text(g.get("vendor")), _text(g.get("driver")), fmt_percent(g.get("busy_percent")), fmt_celsius(g.get("temperature_celsius")), fmt_bytes(g.get("memory_used_bytes")), fmt_bytes(g.get("memory_total_bytes"))] for g in gpus] or [["No GPUs detected"] + [""] * 6])
        powers = [p for p in _as_list(sample.get("power")) if isinstance(p, dict)]
        self._power_table.set_rows([[_text(p.get("name")), fmt_watts(p.get("watts"))] for p in powers] or [["No power sensors", ""]])
        self._system_table.set_rows([["Hostname", _text(system.get("hostname"))], ["Model", _text(system.get("model"))], ["Architecture", _text(system.get("architecture"))], ["Kernel", _text(system.get("kernel"))], ["Uptime", fmt_duration(system.get("uptime_seconds"))], ["Profile", _text(system.get("platform_profile"))]])
        warns = _as_list(sample.get("warnings"))
        self._warnings_label.setText("\n".join("- " + _text(w) for w in warns) if warns else "No warnings")
    def grab_preview(self, path=None):
        path = str(path or os.path.join(os.getcwd(), "laptop-monitor-preview.png"))
        self._tabs.setCurrentIndex(0)
        pix = self.grab()
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        if not pix.save(path, "PNG"):
            raise RuntimeError("failed to write screenshot to %s" % path)
        return path
    def closeEvent(self, event):
        if self._sampling:
            self._close_pending = True
            self._paused = True
            self._timer.stop()
            self._status_label.setText("Finishing collection…")
            event.ignore()
            return
        self.shutdown()
        if event is not None:
            event.accept()
    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._timer.stop()
        except Exception:
            pass
        thread = getattr(self, "_thread", None)
        if thread is not None:
            for sig in ("sampled", "failed", "finished"):
                try:
                    getattr(self._worker, sig).disconnect()
                except (RuntimeError, TypeError):
                    pass
            thread.quit()
            # Keep ownership until the read-only worker finishes; terminating a
            # Python thread can corrupt interpreter state.
            thread.wait()
        self._sampling = False
        self._close_pending = False


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    return app or QtWidgets.QApplication([])

def run_smoke_test(collector=None, timeout=15.0):
    app = _ensure_app()
    window = MonitorWindow(collector=collector, interval=0.25)
    window.show()
    window.refresh_now()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if window.last_sample is not None or window.last_error is not None:
            break
        time.sleep(0.01)
    app.processEvents()
    ok = window.last_sample is not None and window.last_error is None
    window.shutdown()
    window.close()
    app.processEvents()
    return ok

def capture_screenshot(path, collector=None):
    app = _ensure_app()
    window = MonitorWindow(collector=collector, interval=0.25)
    window.show()
    window.refresh_now()
    deadline = time.time() + 15.0
    while time.time() < deadline:
        app.processEvents()
        if (len(window.cpu_history) >= 2) or window.last_error is not None:
            break
        time.sleep(0.01)
    app.processEvents()
    if window.last_sample is None or window.last_error is not None:
        window.shutdown()
        window.close()
        raise RuntimeError(window.last_error or "collection timed out")
    written = window.grab_preview(path)
    window.shutdown()
    window.close()
    return written

def build_parser():
    p = argparse.ArgumentParser(prog="laptop-monitor", description="%s desktop dashboard" % DISPLAY_NAME)
    from .cli import refresh_interval
    p.add_argument("--interval", type=refresh_interval, default=2.0, help="Refresh interval in seconds (default: 2.0)")
    p.add_argument("--smoke-test", action="store_true", help="Run an offscreen self-test and exit")
    p.add_argument("--screenshot", metavar="PATH", default=None, help="Render one frame to a PNG file at PATH and exit")
    return p

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    if args.smoke_test or args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    if args.smoke_test:
        try:
            ok = run_smoke_test()
        except Exception as exc:
            print("smoke test error: %s" % exc, file=sys.stderr)
            return 1
        print("smoke test OK" if ok else "smoke test FAILED", file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    if args.screenshot:
        try:
            written = capture_screenshot(args.screenshot)
        except Exception as exc:
            print("screenshot error: %s" % exc, file=sys.stderr)
            return 1
        print("screenshot written to %s" % written)
        return 0
    window = MonitorWindow(interval=args.interval)
    window.show()
    app.aboutToQuit.connect(window.shutdown)
    return int(app.exec())

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
