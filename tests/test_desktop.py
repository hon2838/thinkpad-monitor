"""Desktop UI tests (unittest, offscreen). Uses a fake collector; no hardware access."""
import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets, QtCore

from thinkpad_monitor import desktop
from thinkpad_monitor.desktop import (
    CPU_HISTORY_LIMIT,
    MonitorWindow,
    SampleWorker,
    UNAVAILABLE,
)


def make_sample(**over):
    sample = {
        "system": {"hostname": "testhost", "model": "TestBook", "architecture": "x86_64",
                   "kernel": "6.0", "uptime_seconds": 3600, "platform_profile": "balanced"},
        "cpu": {"percent": 42.0, "per_core_percent": [40.0, 44.0],
                "frequencies_mhz": [2400.0, 2500.0], "load_average": [0.5, 0.4, 0.3],
                "governor": "schedutil", "driver": "intel_pstate"},
        "memory": {"total_bytes": 8 * 1024**3, "used_bytes": 4 * 1024**3,
                   "available_bytes": 4 * 1024**3, "percent": 50.0,
                   "swap_total_bytes": 2 * 1024**3, "swap_used_bytes": 0, "swap_percent": 0.0},
        "storage": {"total_bytes": 512 * 1024**3, "used_bytes": 100 * 1024**3, "percent": 20.0,
                    "read_bytes_per_second": 1000.0, "write_bytes_per_second": 2000.0},
        "networks": [{"name": "wlan0", "addresses": ["192.168.1.2"], "is_up": True,
                      "rx_bytes_per_second": 100.0, "tx_bytes_per_second": 50.0,
                      "received_bytes": 1000, "sent_bytes": 500}],
        "batteries": [{"name": "BAT0", "status": "Discharging", "percent": 80.0,
                       "health_percent": 95.0, "cycles": 100, "voltage_volts": 12.0,
                       "power_watts": 10.0, "energy_wh": 40.0, "full_energy_wh": 50.0,
                       "time_remaining_seconds": 7200}],
        "temperatures": [{"name": "k10temp-temp1", "label": "Tctl", "celsius": 55.0,
                          "critical_celsius": 100.0}],
        "fans": [{"name": "thinkpad-fan1", "label": "fan1", "rpm": 2500.0}],
        "gpus": [{"name": "card0", "vendor": "AMD", "driver": "amdgpu", "busy_percent": 10.0,
                  "temperature_celsius": 50.0, "memory_used_bytes": 512 * 1024**2,
                  "memory_total_bytes": 4 * 1024**3}],
        "power": [{"name": "package-0", "watts": 12.5}],
        "warnings": [],
    }
    sample.update(over)
    return sample


class FakeCollector:
    """Thread-safe fake collector recording calls and thread ids."""

    def __init__(self, sample=None, delay=0.0, block_event=None):
        self._sample = sample if sample is not None else make_sample()
        self.delay = delay
        self.block_event = block_event
        self.calls = 0
        self.thread_ids = []
        self._lock = threading.Lock()

    def sample(self):
        with self._lock:
            self.calls += 1
        self.thread_ids.append(threading.get_ident())
        if self.block_event is not None:
            self.block_event.wait(10.0)
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self._sample, Exception):
            raise self._sample
        if callable(self._sample):
            return self._sample()
        return self._sample


def ensure_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def wait_for(predicate, timeout=10.0, app=None):
    app = app or ensure_app()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


class DesktopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def setUp(self):
        self.windows = []

    def tearDown(self):
        for w in self.windows:
            try:
                w.shutdown()
            except Exception:
                pass
            try:
                w.close()
            except Exception:
                pass
        ensure_app().processEvents()

    def _window(self, collector=None, interval=10.0):
        w = MonitorWindow(collector=collector or FakeCollector(), interval=interval)
        self.windows.append(w)
        return w

    def test_worker_runs_off_ui_thread(self):
        app = ensure_app()
        ui_thread = threading.get_ident()
        collector = FakeCollector(delay=0.01)
        window = self._window(collector, interval=10.0)
        window.show()
        window.refresh_now()
        ok = wait_for(lambda: window.last_sample is not None, timeout=10.0, app=app)
        self.assertTrue(ok, "expected a sample to arrive")
        self.assertTrue(collector.thread_ids, "collector.sample() was never called")
        for tid in collector.thread_ids:
            self.assertNotEqual(tid, ui_thread, "sample ran on the UI thread")
        # Worker object itself must live on the persistent QThread.
        self.assertEqual(window._worker.thread(), window._thread)
        self.assertNotEqual(window._thread, QtCore.QThread.currentThread())

    def test_request_signal_is_queued_class_signal(self):
        # Regression guard: request must be a class-level Signal, and the slot
        # must be a Qt Slot so emits are queued to the worker thread.
        self.assertIn("request", SampleWorker.__dict__)
        self.assertIn("sampled", SampleWorker.__dict__)
        worker = SampleWorker(FakeCollector(), parent=None)
        try:
            self.assertTrue(hasattr(worker.request, "emit"))
            self.assertTrue(hasattr(worker.sampled, "emit"))
        finally:
            worker.deleteLater()

    def test_nonoverlap_slow_collector(self):
        app = ensure_app()
        gate = threading.Event()
        collector = FakeCollector(delay=0.0, block_event=gate)
        window = self._window(collector, interval=10.0)
        window.show()
        window.refresh_now()  # first sample blocks inside worker
        self.assertTrue(wait_for(lambda: collector.calls >= 1, timeout=5.0, app=app))
        # Give the worker a moment to set busy, then fire overlapping requests.
        time.sleep(0.1)
        app.processEvents()
        self.assertTrue(window._worker.busy, "worker should be busy during slow sample")
        window.refresh_now()
        window.refresh_now()
        app.processEvents()
        time.sleep(0.2)
        app.processEvents()
        calls_while_blocked = collector.calls
        gate.set()  # release the slow sample
        self.assertTrue(wait_for(lambda: window.last_sample is not None, timeout=10.0, app=app))
        # Overlapping requests must have been skipped: only one collection ran.
        self.assertEqual(calls_while_blocked, 1)
        self.assertEqual(collector.calls, 1)

    def test_shutdown_stops_thread_cleanly(self):
        app = ensure_app()
        window = self._window(FakeCollector(), interval=10.0)
        window.show()
        self.assertTrue(window._thread.isRunning())
        window.shutdown()
        app.processEvents()
        self.assertFalse(window._thread.isRunning())
        # Double shutdown must be safe.
        window.shutdown()
        self.assertFalse(window._thread.isRunning())

    def test_pause_resume_and_interval(self):
        app = ensure_app()
        collector = FakeCollector()
        window = self._window(collector, interval=10.0)
        window.show()
        self.assertFalse(window.paused)
        window.toggle_pause()
        self.assertTrue(window.paused)
        calls = collector.calls
        window._tick()
        app.processEvents()
        self.assertEqual(collector.calls, calls, "tick while paused must not sample")
        window.toggle_pause()
        self.assertFalse(window.paused)
        idx = window._interval_combo.findData(5.0)
        window._interval_combo.setCurrentIndex(idx)
        app.processEvents()
        self.assertAlmostEqual(window.interval, 5.0)
        # Manual refresh works even while paused.
        window.toggle_pause()
        window.refresh_now()
        self.assertTrue(wait_for(lambda: window.last_sample is not None, timeout=10.0, app=app))

    def test_multiple_batteries_sensors_rendered(self):
        window = self._window(FakeCollector(), interval=10.0)
        sample = make_sample(
            batteries=[
                {"name": "BAT0", "status": "Discharging", "percent": 80.0,
                 "health_percent": 95.0, "cycles": 100, "voltage_volts": 12.1,
                 "power_watts": 10.0, "energy_wh": 40.0, "full_energy_wh": 50.0,
                 "time_remaining_seconds": 7200},
                {"name": "BAT1", "status": "Charging", "percent": 55.0,
                 "health_percent": 88.0, "cycles": 250, "voltage_volts": 11.4,
                 "power_watts": 25.0, "energy_wh": 22.0, "full_energy_wh": 40.0,
                 "time_remaining_seconds": 1800},
            ],
            temperatures=[
                {"name": "k10temp-temp1", "label": "Tctl", "celsius": 55.0, "critical_celsius": 100.0},
                {"name": "acpitz-thermal_zone0", "label": "x86_pkg_temp", "celsius": 48.0, "critical_celsius": 105.0},
            ],
            fans=[
                {"name": "thinkpad-fan1", "label": "fan1", "rpm": 2500.0},
                {"name": "thinkpad-fan2", "label": "fan2", "rpm": 2700.0},
            ],
            networks=[
                {"name": "wlan0", "addresses": ["192.168.1.2"], "is_up": True,
                 "rx_bytes_per_second": 100.0, "tx_bytes_per_second": 50.0,
                 "received_bytes": 1000, "sent_bytes": 500},
                {"name": "eth0", "addresses": [], "is_up": False,
                 "rx_bytes_per_second": 0.0, "tx_bytes_per_second": 0.0,
                 "received_bytes": 0, "sent_bytes": 0},
            ],
            gpus=[
                {"name": "card0", "vendor": "AMD", "driver": "amdgpu", "busy_percent": 10.0,
                 "temperature_celsius": 50.0, "memory_used_bytes": 1, "memory_total_bytes": 2},
                {"name": "card1", "vendor": "Intel", "driver": "i915", "busy_percent": None,
                 "temperature_celsius": None, "memory_used_bytes": None, "memory_total_bytes": None},
            ],
        )
        window._on_sample(sample)
        self.assertEqual(window._battery_table.rowCount(), 2)
        self.assertEqual(window._temp_table.rowCount(), 2)
        self.assertEqual(window._fan_table.rowCount(), 2)
        self.assertEqual(window._net_table.rowCount(), 2)
        self.assertEqual(window._gpu_table.rowCount(), 2)
        # Second GPU has missing readings -> Unavailable must appear.
        texts = [window._gpu_table.item(1, c).text() for c in range(window._gpu_table.columnCount())]
        self.assertIn(UNAVAILABLE, texts)

    def test_missing_readings_show_unavailable(self):
        window = self._window(FakeCollector(), interval=10.0)
        sample = make_sample(
            cpu={"percent": None, "per_core_percent": [], "frequencies_mhz": [],
                 "load_average": [None, None, None], "governor": None, "driver": None},
            memory={"total_bytes": None, "used_bytes": None, "available_bytes": None,
                    "percent": None, "swap_total_bytes": None, "swap_used_bytes": None,
                    "swap_percent": None},
            storage={"total_bytes": None, "used_bytes": None, "percent": None,
                     "read_bytes_per_second": None, "write_bytes_per_second": None},
            networks=[],
            batteries=[],
            temperatures=[],
            fans=[],
            gpus=[{"name": "card0", "vendor": None, "driver": None, "busy_percent": None,
                   "temperature_celsius": None, "memory_used_bytes": None,
                   "memory_total_bytes": None}],
            power=[],
            warnings=["cpu: percent unavailable: test"],
        )
        window._on_sample(sample)
        for key in ("cpu", "memory", "storage", "battery", "temp", "net", "gpu", "fan"):
            self.assertIn(UNAVAILABLE, window._cards[key].value_text,
                          "card %s should show Unavailable" % key)
        self.assertIn("test", window._warnings_label.text())

    def test_cpu_history_bounded(self):
        window = self._window(FakeCollector(), interval=10.0)
        base = make_sample()
        for i in range(CPU_HISTORY_LIMIT + 50):
            s = make_sample(cpu=dict(base["cpu"], percent=float(i % 101)))
            window._on_sample(s)
        self.assertLessEqual(len(window.cpu_history), CPU_HISTORY_LIMIT)
        self.assertEqual(len(window.cpu_history), CPU_HISTORY_LIMIT)
        # None samples must not grow history.
        before = list(window.cpu_history)
        window._on_sample(make_sample(cpu=dict(base["cpu"], percent=None)))
        self.assertEqual(window.cpu_history, before)


if __name__ == "__main__":
    unittest.main()
