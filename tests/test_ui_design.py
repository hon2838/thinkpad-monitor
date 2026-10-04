"""Interaction checks for the adaptive desktop redesign."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from thinkpad_monitor.desktop import MonitorWindow, build_parser, _settings_interval
from thinkpad_monitor import cli
from test_desktop import FakeCollector, ensure_app, make_sample, wait_for


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.app = ensure_app()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.shutdown()
            window.close()
        self.app.processEvents()

    def window(self, **kwargs):
        window = MonitorWindow(collector=FakeCollector(), interval=60, **kwargs)
        self.windows.append(window)
        return window

    def test_adaptive_navigation_keeps_selected_page(self):
        window = self.window()
        window.resize(1100, 800)
        window.show()
        self.app.processEvents()
        self.assertTrue(window._navigation.isVisible())
        self.assertFalse(window._page_picker.isVisible())
        window._navigation.setCurrentRow(5)
        self.assertEqual(window._tabs.currentIndex(), 5)
        window.resize(480, 640)
        self.app.processEvents()
        self.assertFalse(window._navigation.isVisible())
        self.assertTrue(window._page_picker.isVisible())
        self.assertEqual(window._page_picker.currentIndex(), 5)
        window._page_picker.setCurrentIndex(3)
        self.assertEqual(window._tabs.currentIndex(), 3)
        self.assertEqual(window._navigation.currentRow(), 3)

    def test_paused_status_survives_manual_refresh(self):
        window = self.window()
        window.toggle_pause()
        window._on_sample(make_sample())
        self.assertTrue(window.paused)
        self.assertIn('Paused', window._status_label.text())
        self.assertFalse(window._timer.isActive())
        self.assertIn('Resume', window._pause_button.accessibleName())

    def test_error_and_stale_status_preserve_last_readings(self):
        window = self.window()
        window._on_sample(make_sample())
        window._on_failure('sensor timeout')
        self.assertIn('Collection failed', window._status_label.text())
        self.assertIn('stale', window._notice_label.text())
        self.assertEqual(window._cards['cpu'].value_text, '42%')
        window._on_sample(make_sample())
        self.assertIn('Live', window._status_label.text())
        window._last_updated = time.monotonic() - 181
        window._update_status()
        self.assertIn('Waiting', window._status_label.text())

    def test_keyboard_refresh_pause_and_filter(self):
        window = self.window()
        window.show()
        window.activateWindow()
        self.app.processEvents()
        QtTest.QTest.keyClick(window, QtCore.Qt.Key.Key_P, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(window.paused)
        window._select_page(1)
        QtTest.QTest.keyClick(window, QtCore.Qt.Key.Key_F, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(window._cpu_table.filter_edit.hasFocus())
        window._cpu_table.filter_edit.setText('Core 1')
        window._on_sample(make_sample())
        self.assertTrue(any(not window._cpu_table.isRowHidden(row) and window._cpu_table.item(row, 0).text() == 'Core 1'
                            for row in range(window._cpu_table.rowCount())))

    def test_cpu_rows_remain_individually_readable(self):
        window = self.window()
        window._on_sample(make_sample(cpu={'percent': 50, 'per_core_percent': [float(i) for i in range(32)],
                                          'frequencies_mhz': [2000] * 32}))
        self.assertEqual(window._cpu_table.rowCount(), 36)
        self.assertEqual(window._cpu_table.item(35, 0).text(), 'Core 31')
        self.assertIn('31%', window._cpu_table.item(35, 1).text())

    def test_compact_controls_fit_enlarged_system_font(self):
        previous = self.app.font()
        enlarged = QtGui.QFont(previous)
        enlarged.setPointSize(14)
        self.app.setFont(enlarged)
        try:
            window = self.window()
            window.resize(360, 640)
            window.show()
            window._on_sample(make_sample())
            self.app.processEvents()
            self.assertEqual(window.width(), 360)
            self.assertGreater(window._status_label.y(), window._title_label.y())
            self.assertLess(window._page_picker.y(), window._pause_button.y())
            for control in (window._page_picker, window._pause_button, window._refresh_button,
                            window._interval_combo):
                self.assertLessEqual(control.geometry().right(), window.width())
            overview = window._tabs.currentWidget()
            for width in (360, 480):
                window.resize(width, 640)
                self.app.processEvents()
                self.assertEqual(overview.horizontalScrollBar().maximum(), 0)
        finally:
            self.app.setFont(previous)

    def test_graph_breaks_on_pause_and_collection_failure(self):
        window = self.window()
        window._on_sample(make_sample())
        window.toggle_pause()
        window._on_sample(make_sample())
        self.assertIn(1, window._graph._breaks)
        window._on_failure('failed')
        window._on_sample(make_sample())
        self.assertIn(2, window._graph._breaks)

    def test_restore_page_geometry_and_interval_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QtCore.QSettings(directory + '/settings.ini', QtCore.QSettings.Format.IniFormat)
            first = self.window(settings=settings)
            first._select_page(4)
            first.resize(700, 620)
            first.shutdown()
            second = self.window(settings=settings)
            self.assertEqual(second._tabs.currentIndex(), 4)
            self.assertEqual(second.size(), first.size())
            self.assertEqual(float(settings.value('monitor/interval')), 60)

    def test_launch_interval_settings_and_explicit_cli_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QtCore.QSettings(directory + '/settings.ini', QtCore.QSettings.Format.IniFormat)
            settings.setValue('monitor/interval', 10)
            self.assertEqual(_settings_interval(build_parser().parse_args([]), settings), 10)
            for spelling in (['--interval', '5'], ['--interval=5']):
                self.assertEqual(_settings_interval(build_parser().parse_args(spelling), settings), 5)
            for invalid in ('nan', 'inf', 0, 100, 'bad'):
                settings.setValue('monitor/interval', invalid)
                self.assertEqual(_settings_interval(build_parser().parse_args([]), settings), 2)

    def test_shared_launcher_only_forwards_explicit_interval(self):
        for arguments, expected in (([], []), (['--interval=5'], ['--interval', '5.0'])):
            with self.subTest(arguments=arguments), patch.dict(os.environ, {'DISPLAY': ':1'}), \
                    patch('thinkpad_monitor.desktop.main', return_value=0) as desktop:
                self.assertEqual(cli.main(['--desktop', *arguments]), 0)
                desktop.assert_called_once_with(expected)

    def test_live_data_is_plain_text_and_controls_named(self):
        window = self.window()
        window._on_sample(make_sample(system={'hostname': '<b>host</b>', 'model': 'Laptop', 'architecture': 'arm64'}))
        self.assertEqual(window._host_value.textFormat(), QtCore.Qt.TextFormat.PlainText)
        for widget in (window._page_picker, window._navigation, window._pause_button, window._refresh_button,
                       window._interval_combo, window._status_label):
            self.assertTrue(widget.accessibleName())
        self.assertIn('42%', window._cards['cpu'].accessibleDescription())
