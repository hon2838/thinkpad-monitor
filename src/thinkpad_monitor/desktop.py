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


from .ui_components import SummaryCard, UsageBar, CpuGraph, DetailTable


class MonitorWindow(QtWidgets.QMainWindow):
    def __init__(self, collector=None, interval=2.0, parent=None, settings=None):
        super().__init__(parent)
        self._settings = settings
        self._last_updated = None
        self._page_descriptions = {}
        self._shortcuts = []
        self._interval = max(0.25, float(interval))
        self._paused = False
        self._last_sample = None
        self._error = None
        self._shutting_down = False
        self._sampling = False
        self._close_pending = False
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1100, 800)
        self.setMinimumSize(360, 360)
        if collector is None:
            from .telemetry import Collector
            collector = Collector()
        self._collector = collector
        self._build_ui()
        self._build_worker()
        self._apply_interval()
        self._freshness_timer = QtCore.QTimer(self)
        self._freshness_timer.setInterval(1000)
        self._freshness_timer.timeout.connect(self._update_status)
        self._freshness_timer.start()
        if self._settings is not None:
            geometry = self._settings.value("window/geometry")
            if isinstance(geometry, QtCore.QByteArray):
                self.restoreGeometry(geometry)
            try:
                self._select_page(int(self._settings.value("window/page", 0)))
            except (ValueError, TypeError):
                pass
        self._reflow()
        QtCore.QTimer.singleShot(0, self._tick)
    def _build_ui(self):
        central = QtWidgets.QWidget()
        central.setObjectName("appShell")
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        heading = QtWidgets.QHBoxLayout()
        self._title_label = QtWidgets.QLabel(DISPLAY_NAME)
        font = self._title_label.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        self._title_label.setFont(font)
        self._title_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        heading.addWidget(self._title_label)
        heading.addStretch()
        self._status_label = QtWidgets.QLabel("Starting…")
        self._status_label.setAccessibleName("Monitoring status")
        self._status_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._status_label.setWordWrap(True)
        heading.addWidget(self._status_label)
        root.addLayout(heading)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(8)
        controls.addStretch(1)
        self._page_picker = QtWidgets.QComboBox()
        self._page_picker.setAccessibleName("Monitoring page")
        self._page_picker.currentIndexChanged.connect(self._select_page)
        controls.addWidget(self._page_picker, 1)
        self._pause_button = QtWidgets.QPushButton("Pause")
        self._pause_button.setAccessibleName("Pause monitoring")
        self._pause_button.setToolTip("Pause or resume monitoring (Ctrl+P)")
        self._pause_button.clicked.connect(self.toggle_pause)
        controls.addWidget(self._pause_button)
        self._refresh_button = QtWidgets.QPushButton("Refresh")
        self._refresh_button.setAccessibleName("Refresh readings")
        self._refresh_button.setToolTip("Collect readings now (Ctrl+R)")
        self._refresh_button.clicked.connect(self.refresh_now)
        controls.addWidget(self._refresh_button)
        self._interval_combo = QtWidgets.QComboBox()
        for seconds in (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0):
            self._interval_combo.addItem("%g s" % seconds, seconds)
        self._interval_combo.setAccessibleName("Refresh interval")
        self._interval_combo.setToolTip("Time between collections")
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        controls.addWidget(self._interval_combo)
        root.addLayout(controls)

        content = QtWidgets.QHBoxLayout()
        content.setSpacing(16)
        self._navigation = QtWidgets.QListWidget()
        self._navigation.setObjectName("navigation")
        self._navigation.setAccessibleName("Monitoring pages")
        self._navigation.setFixedWidth(166)
        self._navigation.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._navigation.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._navigation.currentRowChanged.connect(self._select_page)
        content.addWidget(self._navigation)
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.setObjectName("pages")
        self._tabs.tabBar().hide()
        self._tabs.currentChanged.connect(self._sync_navigation)
        content.addWidget(self._tabs, 1)
        root.addLayout(content, 1)

        self._build_summary_tab()
        self._cpu_table = self._table_tab("Processor", ["Metric", "Value"], "CPU activity, frequency and individual cores")
        self._mem_table = self._table_tab("Memory", ["Metric", "Value"], "Memory available to apps and swap usage")
        self._storage_table = self._table_tab("Storage", ["Metric", "Value"], "Root filesystem capacity and system disk activity")
        self._battery_table = self._table_tab("Batteries", ["Name", "Status", "Charge", "Health", "Cycles", "Voltage", "Power", "Energy (Wh)", "Estimated time"], "Each battery pack, its health and power use")
        self._net_table = self._table_tab("Network", ["Interface", "Connected", "Addresses", "Download", "Upload", "Received", "Sent"], "All interfaces and their measured transfer rates")
        layout = self._add_scroll_tab("Thermals", "Temperatures and fan speeds reported by your device")
        self._temp_table = DetailTable(["Sensor", "Label", "Temperature", "Critical limit"])
        layout.addWidget(self._detail_panel("Temperatures", self._temp_table))
        self._fan_table = DetailTable(["Fan", "Label", "Speed"])
        layout.addWidget(self._detail_panel("Cooling fans", self._fan_table))
        self._gpu_table = self._table_tab("Graphics", ["GPU", "Vendor", "Driver", "Activity", "Temperature", "VRAM used", "VRAM total"], "Graphics devices and available driver readings")
        self._power_table = self._table_tab("Power", ["Domain", "Measured watts"], "Actual sensor readings; availability depends on your hardware")
        system_layout = self._add_scroll_tab("System", "Device information and sensor availability")
        self._system_table = DetailTable(["Field", "Value"])
        system_layout.addWidget(self._detail_panel("Device", self._system_table))
        self._warnings_label = QtWidgets.QLabel("")
        self._warnings_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._warnings_label.setAccessibleName("Sensor availability details")
        system_layout.addWidget(self._section_title("Sensor availability"))
        system_layout.addWidget(self._warnings_label)
        system_layout.addStretch()

        self._notice_label = QtWidgets.QLabel("Readings stay on this device · no hardware settings are changed")
        self._notice_label.setWordWrap(True)
        self._notice_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._notice_label.setAccessibleName("Monitoring information")
        root.addWidget(self._notice_label)
        self._install_shortcuts()
        self._select_page(0)
        self._apply_theme()

    @staticmethod
    def _section_title(text):
        label = QtWidgets.QLabel(text)
        label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        font = label.font()
        font.setPointSizeF(font.pointSizeF() + 1)
        font.setBold(True)
        label.setFont(font)
        return label

    def _apply_theme(self):
        self.setStyleSheet("""
            QFrame#metricCard, QFrame#historyPanel, QFrame#detailPanel {
                background: palette(base); border: 1px solid palette(mid);
                border-radius: 12px;
            }
            QTabWidget#pages::pane { border: 0; }
            QListWidget#navigation { border: 0; background: palette(window); }
            QListWidget#navigation::item { padding: 10px 12px; margin: 2px;
                border: 2px solid transparent; border-radius: 8px; }
            QListWidget#navigation::item:selected { background: palette(highlight);
                color: palette(highlighted-text); }
            QListWidget#navigation::item:focus { border: 2px solid palette(text); }
            QPushButton, QComboBox, QLineEdit { min-height: 28px; }
        """)

    def _add_scroll_tab(self, title, description=""):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(4, 0, 4, 4)
        layout.setSpacing(16)
        layout.addWidget(self._section_title(title))
        if description:
            subtitle = QtWidgets.QLabel(description)
            subtitle.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            subtitle.setWordWrap(True)
            layout.addWidget(subtitle)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        scroll.setAccessibleName(title + " page")
        index = self._tabs.addTab(scroll, title)
        self._page_descriptions[index] = description
        self._navigation.addItem(title)
        self._page_picker.addItem(title)
        return layout

    def _detail_panel(self, title, table):
        panel = QtWidgets.QFrame()
        panel.setObjectName("detailPanel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        bar = QtWidgets.QHBoxLayout()
        search = QtWidgets.QLineEdit()
        search.setPlaceholderText("Filter " + title.lower())
        search.setClearButtonEnabled(True)
        search.setAccessibleName("Filter " + title.lower())
        search.textChanged.connect(table.apply_filter)
        table.setAccessibleName(title)
        table.filter_edit = search
        bar.addWidget(search, 1)
        copy = QtWidgets.QPushButton("Copy rows")
        copy.setAccessibleName("Copy selected " + title.lower() + " rows")
        copy.setToolTip("Copy selected rows with column names (Ctrl+C)")
        copy.clicked.connect(table.copy_selected)
        bar.addWidget(copy)
        layout.addLayout(bar)
        layout.addWidget(table, 1)
        table.setMinimumHeight(200)
        return panel

    def _table_tab(self, title, headers, description=""):
        layout = self._add_scroll_tab(title, description)
        table = DetailTable(headers)
        layout.addWidget(self._detail_panel(title, table), 1)
        return table

    def _build_summary_tab(self):
        layout = self._add_scroll_tab("Overview", "A live view of your laptop’s activity and condition")
        self._host_value = QtWidgets.QLabel("Discovering this device…")
        self._host_value.setWordWrap(True)
        self._host_value.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._host_value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self._host_value.setAccessibleName("Device identity")
        layout.addWidget(self._host_value)
        self._summary_grid = QtWidgets.QGridLayout()
        self._summary_grid.setSpacing(12)
        layout.addLayout(self._summary_grid)
        self._cards = {}
        titles = (("cpu", "Processor"), ("memory", "Memory"), ("battery", "Battery"),
                  ("storage", "Storage"), ("temp", "Hottest sensor"), ("net", "Network"),
                  ("gpu", "Graphics"), ("fan", "Cooling"))
        for index, (key, title) in enumerate(titles):
            card = SummaryCard(title)
            card.setObjectName("metricCard")
            card.bar.setTextVisible(False)
            card.bar.setFixedHeight(8)
            card.setAccessibleName(title + " summary")
            self._cards[key] = card
            self._summary_grid.addWidget(card, index // 4, index % 4)
        self._cpu_bar = self._cards['cpu'].bar
        self._mem_bar = self._cards['memory'].bar
        self._battery_bar = self._cards['battery'].bar
        for key in ('storage', 'temp', 'net', 'gpu', 'fan'):
            self._cards[key].bar.hide()
        panel = QtWidgets.QFrame()
        panel.setObjectName("historyPanel")
        graph_layout = QtWidgets.QVBoxLayout(panel)
        graph_layout.setContentsMargins(20, 16, 20, 16)
        graph_layout.addWidget(self._section_title("Processor activity"))
        graph_layout.addWidget(QtWidgets.QLabel("Recent readings · gaps indicate paused or unavailable data"))
        self._graph = CpuGraph()
        graph_layout.addWidget(self._graph)
        layout.addWidget(panel)
        layout.addStretch()

    def _select_page(self, index):
        if hasattr(self, '_tabs') and 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)
            self._sync_navigation(index)

    def _sync_navigation(self, index):
        for widget, setter in ((self._navigation, self._navigation.setCurrentRow),
                               (self._page_picker, self._page_picker.setCurrentIndex)):
            previous = widget.blockSignals(True)
            setter(index)
            widget.blockSignals(previous)

    def _install_shortcuts(self):
        for sequence, action in (("Ctrl+R", self.refresh_now), ("Ctrl+P", self.toggle_pause),
                                 ("Ctrl+W", self.close), ("Ctrl+F", self._focus_filter),
                                 ("Alt+Left", lambda: self._select_page(max(0, self._tabs.currentIndex() - 1))),
                                 ("Alt+Right", lambda: self._select_page(min(self._tabs.count() - 1, self._tabs.currentIndex() + 1)))):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)

    def _focus_filter(self):
        page = self._tabs.currentWidget()
        search = page.findChild(QtWidgets.QLineEdit) if page is not None else None
        if search is not None:
            search.setFocus()
            search.selectAll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self):
        if not hasattr(self, '_summary_grid'):
            return
        wide = self.width() >= 820
        self._navigation.setVisible(wide)
        self._page_picker.setVisible(not wide)
        available = max(0, self.width() - (214 if wide else 44))
        minimum = max(180, int(self.fontMetrics().horizontalAdvance("Unavailable") * 1.5))
        columns = 4 if available >= 4 * minimum else 2 if available >= 2 * minimum else 1
        for column in range(4):
            self._summary_grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, key in enumerate(("cpu", "memory", "battery", "storage", "temp", "net", "gpu", "fan")):
            self._summary_grid.addWidget(self._cards[key], index // columns, index % columns)

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
        self._update_status()
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
        self._paused = not self._paused
        self._pause_button.setText("Resume" if self._paused else "Pause")
        self._pause_button.setAccessibleName("Resume monitoring" if self._paused else "Pause monitoring")
        if self._paused:
            self._timer.stop()
            self._graph.gap()
        else:
            self._tick()
        self._update_status()
        return self._paused

    def _update_status(self):
        if self._shutting_down:
            return
        age = None if self._last_updated is None else max(0, time.monotonic() - self._last_updated)
        if self._error:
            status = "Collection failed"
            detail = "Last readings may be stale · press Refresh to retry"
        elif self._paused:
            status = "Paused"
            detail = "Automatic collection is paused"
        elif age is None:
            status = "Starting"
            detail = "Discovering available sensors"
        elif age > max(10, self._interval * 3):
            status = "Waiting for readings"
            detail = "Last collection %s ago" % fmt_duration(age)
        else:
            status = "Live"
            detail = "Updated just now" if age < 2 else "Updated %s ago" % fmt_duration(age)
        self._status_label.setText(status + " · " + detail)
        self._status_label.setAccessibleDescription(status + ". " + detail)

    def refresh_now(self):
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
        self._last_updated = time.monotonic()
        self._error = None
        self._render(sample)
        self._update_status()
    def _on_failure(self, message):
        self._error = message
        self._graph.gap()
        self._update_status()
        self._notice_label.setText("Collection failed. Existing readings may be stale. Press Refresh to retry.")
        self._warnings_label.setText("Last collection failed: %s" % message)
    def _render(self, sample):
        system, cpu = _section(sample, "system"), _section(sample, "cpu")
        memory, storage = _section(sample, "memory"), _section(sample, "storage")
        self._host_value.setText("%s \u2014 %s (%s)" % (_text(system.get("hostname")), _text(system.get("model")), _text(system.get("architecture"))))
        bits = [t for t in ((_text(cpu["governor"]) if cpu.get("governor") is not None else UNAVAILABLE), (_text(cpu["driver"]) if cpu.get("driver") is not None else UNAVAILABLE)) if t != UNAVAILABLE]
        self._cards["cpu"].set_value(fmt_percent(cpu.get("percent")), " \u00b7 ".join(bits) if bits else None)
        self._cpu_bar.set_usage(cpu.get("percent"), "CPU · " + fmt_percent(cpu.get("percent")))
        self._cards["memory"].set_value(fmt_percent(memory.get("percent")), "%s available of %s" % (fmt_bytes(memory.get("available_bytes")), fmt_bytes(memory.get("total_bytes"))))
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
                detail = "%d packs · shown individually" % len(bats)
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
        self._graph.append(cpu.get("percent"), timestamp=self._last_updated)
        per_core, freqs, load = _as_list(cpu.get("per_core_percent")), _as_list(cpu.get("frequencies_mhz")), _as_list(cpu.get("load_average"))
        cpu_rows = [["Overall activity", fmt_percent(cpu.get("percent"))],
                    ["Load average (1 / 5 / 15 min)", ", ".join(fmt_num(x, 2) for x in load) if load else UNAVAILABLE],
                    ["Governor", _text(cpu.get("governor"))], ["Scaling driver", _text(cpu.get("driver"))]]
        for index in range(max(len(per_core), len(freqs))):
            activity = per_core[index] if index < len(per_core) else None
            frequency = freqs[index] if index < len(freqs) else None
            cpu_rows.append(["Core %d" % index, "%s · %s" % (fmt_percent(activity), fmt_mhz(frequency))])
        self._cpu_table.set_rows(cpu_rows)
        self._mem_table.set_rows([["Total", fmt_bytes(memory.get("total_bytes"))], ["Used", fmt_bytes(memory.get("used_bytes"))], ["Available", fmt_bytes(memory.get("available_bytes"))], ["Used %", fmt_percent(memory.get("percent"))], ["Swap total", fmt_bytes(memory.get("swap_total_bytes"))], ["Swap used", fmt_bytes(memory.get("swap_used_bytes"))], ["Swap %", fmt_percent(memory.get("swap_percent"))]])
        self._storage_table.set_rows([["Total", fmt_bytes(storage.get("total_bytes"))], ["Used", fmt_bytes(storage.get("used_bytes"))], ["Used %", fmt_percent(storage.get("percent"))], ["Read rate", fmt_rate(storage.get("read_bytes_per_second"))], ["Write rate", fmt_rate(storage.get("write_bytes_per_second"))]])
        rows = [[_text(e.get("name")), _text(e.get("status")), fmt_percent(e.get("percent")), fmt_percent(e.get("health_percent")), fmt_int(e.get("cycles")), fmt_volts(e.get("voltage_volts")), fmt_watts(e.get("power_watts")), "%s / %s Wh" % (fmt_num(e.get("energy_wh"), 1), fmt_num(e.get("full_energy_wh"), 1)), fmt_duration(e.get("time_remaining_seconds"))] for e in bats]
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
        self._power_table.set_rows([[_text(p.get("name")), fmt_watts(p.get("watts"))] for p in powers] or [["No readable power sensor", "Unavailable"]])
        self._system_table.set_rows([["Hostname", _text(system.get("hostname"))], ["Model", _text(system.get("model"))], ["Architecture", _text(system.get("architecture"))], ["Kernel", _text(system.get("kernel"))], ["Uptime", fmt_duration(system.get("uptime_seconds"))], ["Profile", _text(system.get("platform_profile"))]])
        warns = _as_list(sample.get("warnings"))
        self._warnings_label.setText("\n".join("• " + _text(w) for w in warns) if warns else "All detected sensor files are readable. Some metrics may still be unavailable if the hardware does not provide them.")
        self._notice_label.setText("Some sensor files cannot be read. See System for details." if warns else
                                   "Readings stay on this device · no hardware settings are changed")
    def grab_preview(self, path=None):
        path = str(path or os.path.join(os.getcwd(), "laptop-monitor-preview.png"))
        self._select_page(0)
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
        if self._settings is not None:
            self._settings.setValue("window/geometry", self.saveGeometry())
            self._settings.setValue("window/page", self._tabs.currentIndex())
            self._settings.setValue("monitor/interval", self._interval)
        if hasattr(self, "_freshness_timer"):
            self._freshness_timer.stop()
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
    settings = QtCore.QSettings("thinkpad-monitor", "Laptop Monitor")
    interval = args.interval
    if "--interval" not in argv:
        try:
            saved_interval = float(settings.value("monitor/interval", interval))
            if 0.5 <= saved_interval <= 60:
                interval = saved_interval
        except (TypeError, ValueError):
            pass
    window = MonitorWindow(interval=interval, settings=settings)
    window.show()
    app.aboutToQuit.connect(window.shutdown)
    return int(app.exec())

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
