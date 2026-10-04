"""Integrator checks for launch and worker request races."""
import os
import time
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtWidgets
from thinkpad_monitor.desktop import MonitorWindow
from test_desktop import FakeCollector, ensure_app, make_sample, wait_for


class DesktopRegressions(unittest.TestCase):
    def setUp(self):
        self.app = ensure_app()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.shutdown()
            window.close()
        self.app.processEvents()

    def window(self, collector=None):
        w = MonitorWindow(collector=collector or FakeCollector(), interval=60)
        self.windows.append(w)
        return w

    def test_collects_on_launch_without_manual_refresh(self):
        window = self.window()
        window.show()
        self.assertTrue(wait_for(lambda: window.last_sample is not None, app=self.app))
        self.assertIn('60', window._interval_combo.currentText())

    def test_rapid_refreshes_do_not_queue_duplicate_samples(self):
        collector = FakeCollector(delay=0.1)
        window = self.window(collector)
        for _ in range(20):
            window.refresh_now()
        self.assertTrue(wait_for(lambda: window.last_sample is not None, app=self.app))
        time.sleep(0.15)
        self.app.processEvents()
        self.assertEqual(collector.calls, 1)

    def test_network_summary_excludes_loopback(self):
        window = self.window()
        window._on_sample(make_sample(networks=[
            {'name': 'lo', 'is_up': True, 'rx_bytes_per_second': 5000},
            {'name': 'wifi0', 'is_up': True, 'rx_bytes_per_second': 50},
        ]))
        self.assertEqual(window._cards['net'].value_text, 'wifi0')

    def test_more_than_64_sensors_are_visible(self):
        window = self.window()
        window._on_sample(make_sample(temperatures=[
            {'name': f'sensor{i}', 'label': 'core', 'celsius': 40}
            for i in range(96)
        ]))
        self.assertEqual(window._temp_table.rowCount(), 96)

    def test_multi_battery_summary_names_each_pack(self):
        window = self.window()
        window._on_sample(make_sample(batteries=[
            {'name': 'BAT0', 'percent': 80, 'status': 'Discharging'},
            {'name': 'BAT1', 'percent': 20, 'status': 'Charging'},
        ]))
        self.assertIn('BAT0 80%', window._cards['battery'].value_text)
        self.assertIn('BAT1 20%', window._cards['battery'].value_text)
        self.assertFalse(window._battery_bar.available)

    def test_shutdown_during_sample_then_close(self):
        collector = FakeCollector(delay=.1)
        window = self.window(collector)
        window.show()
        window.refresh_now()
        self.assertTrue(wait_for(lambda: collector.calls > 0, app=self.app))
        window.shutdown()
        window.close()
        self.assertFalse(window.isVisible())
        self.assertFalse(window._sampling)
        self.assertFalse(window._thread.isRunning())

    def test_summary_reflows_for_small_window(self):
        window = self.window()
        window.resize(640, 600)
        window.show()
        self.app.processEvents()
        position = window._summary_grid.getItemPosition(window._summary_grid.indexOf(window._cards['battery']))
        self.assertEqual(position[:2], (1, 0))
