"""Tests for thinkpad_monitor.ui_icons (offscreen, no hardware)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets
from test_desktop import ensure_app

from thinkpad_monitor import ui_icons
from thinkpad_monitor.ui_icons import ICON_NAMES, available_icons, has_icon, icon


EXPECTED = (
    "overview", "cpu", "memory", "storage", "battery", "network",
    "thermals", "gpu", "power", "system", "fan", "pause",
    "resume", "refresh", "copy", "laptop",
)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_names(self):
        self.assertEqual(tuple(ICON_NAMES), EXPECTED)
        self.assertEqual(set(available_icons()), set(EXPECTED))
        for name in EXPECTED:
            self.assertTrue(has_icon(name), name)
            self.assertTrue(has_icon(name.upper()), name)
        self.assertFalse(has_icon("nope"))

    def test_icon_returns_qicon_and_sizes(self):
        pal = QtGui.QPalette()
        for name in EXPECTED:
            ic = icon(name, pal, size=20)
            self.assertIsInstance(ic, QtGui.QIcon)
            self.assertFalse(ic.isNull())
            pm = ic.pixmap(20, 20)
            self.assertFalse(pm.isNull(), name)
            self.assertEqual(pm.width(), 20)
            avail = ic.availableSizes()
            self.assertTrue(avail, name)
            self.assertEqual(avail[0], QtCore.QSize(20, 20))

    def test_modes_selected_and_disabled(self):
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("red"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("lime"))
        for name in EXPECTED:
            ic = icon(name, pal, size=24)
            for mode in (QtGui.QIcon.Mode.Normal, QtGui.QIcon.Mode.Selected,
                         QtGui.QIcon.Mode.Disabled):
                pm = ic.pixmap(QtCore.QSize(24, 24), mode)
                self.assertFalse(pm.isNull(), (name, mode))

    def test_mode_colors_differ(self):
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#ff0000"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#00ff00"))
        ic = icon("cpu", pal, size=32)
        normal = ic.pixmap(QtCore.QSize(32, 32), QtGui.QIcon.Mode.Normal).toImage()
        selected = ic.pixmap(QtCore.QSize(32, 32), QtGui.QIcon.Mode.Selected).toImage()

        def colors(img):
            out = set()
            for y in range(img.height()):
                for x in range(img.width()):
                    c = QtGui.QColor(img.pixelColor(x, y))
                    if c.alpha() > 32:
                        out.add((c.red() > 128, c.green() > 128, c.blue() > 128))
            return out

        self.assertIn((True, False, False), colors(normal))
        self.assertIn((False, True, False), colors(selected))

    def test_scaled_pixmap_hidpi(self):
        ic = icon("battery", QtGui.QPalette(), size=20)
        engine = None
        # QIconEngine access via clone through pixmap path; exercise scaledPixmap directly.
        from thinkpad_monitor.ui_icons import _VectorEngine

        eng = _VectorEngine("battery", QtGui.QPalette(), 20)
        pm = eng.scaledPixmap(QtCore.QSize(20, 20), QtGui.QIcon.Mode.Normal,
                              QtGui.QIcon.State.Off, 2.0)
        self.assertFalse(pm.isNull())
        self.assertAlmostEqual(pm.devicePixelRatio(), 2.0)
        self.assertEqual(pm.width(), 40)

    def test_errors(self):
        with self.assertRaises(ValueError):
            icon("no-such-icon", QtGui.QPalette())
        with self.assertRaises(ValueError):
            icon("cpu", QtGui.QPalette(), size=0)
        with self.assertRaises((TypeError, ValueError)):
            icon(None, QtGui.QPalette())

if __name__ == "__main__":
    unittest.main()
