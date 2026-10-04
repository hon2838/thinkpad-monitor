"""Regressions for theme switching, scaled icons and status legibility."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtCore, QtGui
from test_desktop import ensure_app, FakeCollector, make_sample, wait_for
from thinkpad_monitor.desktop import MonitorWindow
from thinkpad_monitor.ui_icons import icon


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.app = ensure_app()
        self.original_palette = self.app.palette()
        self.original_font = self.app.font()
        self.window = MonitorWindow(FakeCollector(), interval=60)
        self.window.show()
        self.assertTrue(wait_for(lambda: self.window.last_sample is not None and
                                 not self.window._sampling, app=self.app))

    def tearDown(self):
        self.window.shutdown()
        self.window.close()
        self.app.setPalette(self.original_palette)
        self.app.setFont(self.original_font)
        self.app.processEvents()

    def test_running_window_adapts_to_dark_palette_and_unreadable_muted_role(self):
        palette = QtGui.QPalette(self.original_palette)
        for role, color in (("Window", "#292929"), ("WindowText", "#eeeeee"),
                            ("Base", "#222222"), ("Text", "#eeeeee"),
                            ("PlaceholderText", "#111111")):
            palette.setColor(getattr(QtGui.QPalette.ColorRole, role), QtGui.QColor(color))
        self.app.setPalette(palette)
        self.app.processEvents()
        self.app.processEvents()
        card = self.window._cards["cpu"]
        self.assertEqual(card.palette().color(QtGui.QPalette.ColorRole.Base).name(), "#222222")
        self.assertNotEqual(card._detail.palette().color(QtGui.QPalette.ColorRole.WindowText).name(), "#111111")
        self.assertGreater(card._detail.palette().color(QtGui.QPalette.ColorRole.WindowText).lightness(), 160)
        self.assertEqual(card.value_text, "42%")
        self.app.setPalette(self.original_palette)
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(card.palette().color(QtGui.QPalette.ColorRole.Base),
                         self.original_palette.color(QtGui.QPalette.ColorRole.Base))

    def test_label_icons_request_device_pixel_ratio(self):
        card = self.window._cards["cpu"]
        # QLabel's getter returns a rendering for the current display, so
        # inspect the supplied source pixmap when simulating another DPI.
        with patch.object(card, "devicePixelRatioF", return_value=2.0), \
                patch.object(card._icon_label, "setPixmap", wraps=card._icon_label.setPixmap) as set_card_pixmap:
            card.set_icon(icon("cpu", self.window.palette()))
        pixmap = set_card_pixmap.call_args.args[0]
        self.assertEqual(pixmap.width(), 40)
        self.assertEqual(pixmap.devicePixelRatio(), 2)
        with patch.object(self.window, "devicePixelRatioF", return_value=2.0), \
                patch.object(self.window._device_icon, "setPixmap", wraps=self.window._device_icon.setPixmap) as set_device_pixmap:
            self.window._refresh_icons()
        pixmap = set_device_pixmap.call_args.args[0]
        self.assertEqual(pixmap.width(), 64)
        self.assertEqual(pixmap.devicePixelRatio(), 2)

    def test_status_remains_legible_after_updates_and_large_font(self):
        self.window.toggle_pause()
        self.app.processEvents()
        status = self.window._status_label
        self.assertFalse(status.wordWrap())
        self.assertGreaterEqual(status.width(), status.fontMetrics().horizontalAdvance(status.text()) + 20)
        font = QtGui.QFont(self.original_font)
        font.setPointSize(14)
        self.app.setFont(font)
        self.window.resize(360, 640)
        self.window._on_sample(make_sample())
        self.app.processEvents()
        self.assertTrue(status.wordWrap())
        text = status.fontMetrics().boundingRect(QtCore.QRect(0, 0, status.width() - 20, 1000),
            QtCore.Qt.TextFlag.TextWordWrap, status.text())
        self.assertGreaterEqual(status.height(), text.height() + 12)
        self.assertEqual(self.window._tabs.currentWidget().horizontalScrollBar().maximum(), 0)
