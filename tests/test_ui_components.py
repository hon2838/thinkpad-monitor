"""Tests for thinkpad_monitor.ui_components (offscreen, no hardware)."""
import math
import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets
from test_desktop import ensure_app

from thinkpad_monitor import ui_components
from thinkpad_monitor.ui_components import (
    CPU_HISTORY_LIMIT,
    UNAVAILABLE,
    CpuGraph,
    DetailTable,
    SummaryCard,
    UsageBar,
)


class ExportsTest(unittest.TestCase):
    def test_constants_and_imports(self):
        self.assertEqual(CPU_HISTORY_LIMIT, 180)
        self.assertEqual(UNAVAILABLE, "Unavailable")
        self.assertEqual(ui_components.CPU_HISTORY_LIMIT, 180)
        for name in ("QtCore", "QtGui", "QtWidgets"):
            self.assertTrue(hasattr(ui_components, name), name)


class SummaryCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_api_and_value(self):
        card = SummaryCard("CPU")
        try:
            for attr in ("_title", "_value", "_detail", "bar", "value_text"):
                self.assertTrue(hasattr(card, attr), attr)
            self.assertIsInstance(card.bar, UsageBar)
            card.show()
            ensure_app().processEvents()
            card.set_value("42%", "detail here")
            self.assertEqual(card.value_text, "42%")
            self.assertFalse(card._detail.isHidden())
            card.set_value(None)
            self.assertEqual(card.value_text, UNAVAILABLE)
            card.set_value(float("nan"))
            self.assertEqual(card.value_text, UNAVAILABLE)
            card.set_value(float("inf"), "x")
            self.assertEqual(card.value_text, UNAVAILABLE)
            card.set_value("ok", None)
            self.assertTrue(card._detail.isHidden())
        finally:
            card.deleteLater()

    def test_plain_text_and_policy(self):
        card = SummaryCard("<b>CPU</b>")
        try:
            self.assertEqual(card._title.textFormat(), QtCore.Qt.TextFormat.PlainText)
            self.assertEqual(card._value.textFormat(), QtCore.Qt.TextFormat.PlainText)
            self.assertEqual(card.objectName(), "SummaryCard")
            self.assertTrue(card.accessibleName())
            self.assertTrue(card.accessibleDescription())
            h, v = card.sizePolicy().horizontalPolicy(), card.sizePolicy().verticalPolicy()
            self.assertEqual(h, QtWidgets.QSizePolicy.Policy.Expanding)
            self.assertEqual(v, QtWidgets.QSizePolicy.Policy.Preferred)
            self.assertGreaterEqual(card._value.font().pointSizeF(), 12.0)
            card.set_value("7%", "d")
            self.assertIn("7%", card.accessibleDescription())
        finally:
            card.deleteLater()


class UsageBarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_usage(self):
        bar = UsageBar()
        try:
            bar.set_usage(42.0)
            self.assertTrue(bar.available)
            self.assertEqual(bar.value(), 42)
            bar.set_usage(None)
            self.assertFalse(bar.available)
            self.assertEqual(bar.format(), UNAVAILABLE)
            for bad in (float("nan"), float("inf"), "nope"):
                bar.set_usage(bad)
                self.assertFalse(bar.available, repr(bad))
            bar.set_usage(150, "CPU · 150%")
            self.assertTrue(bar.available)
            self.assertEqual(bar.value(), 100)
            bar.set_usage(-5)
            self.assertEqual(bar.value(), 0)
            bar.set_usage(33.3, "custom")
            self.assertEqual(bar.format(), "custom")
        finally:
            bar.deleteLater()


class CpuGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_append_samples_limit(self):
        g = CpuGraph(limit=5)
        try:
            self.assertEqual(g.samples, [])
            g.append(10, timestamp=1000.0)
            g.append(20, timestamp=1001.0)
            self.assertEqual(g.samples, [10.0, 20.0])
            # Missing / non-finite are skipped.
            g.append(None, timestamp=1002.0)
            g.append(float("nan"), timestamp=1003.0)
            g.append(float("inf"))
            g.append("bad")
            self.assertEqual(g.samples, [10.0, 20.0])
            # Next known reading starts a new segment.
            g.append(30, timestamp=1004.0)
            self.assertEqual(g.samples, [10.0, 20.0, 30.0])
            self.assertTrue(g._breaks, "missing readings should break segments")
            for i in range(10):
                g.append(float(i), timestamp=2000.0 + i)
            self.assertLessEqual(len(g.samples), 5)
            self.assertEqual(len(g.samples), 5)
        finally:
            g.deleteLater()

    def test_gap_and_clear_and_times(self):
        g = CpuGraph(limit=10)
        try:
            g.append(10, timestamp=5000.0)
            g.append(20, timestamp=5001.0)
            g.gap()
            g.append(30, timestamp=5002.0)
            self.assertIn(2, g._breaks)
            before = list(g.timestamps)
            # Times are retained verbatim (never re-timed).
            g.append(40, timestamp=5003.0)
            self.assertEqual(g.timestamps[:3], before)
            self.assertEqual(g.timestamps[0], 5000.0)
            self.assertTrue(all(b > a for a, b in zip(g.timestamps, g.timestamps[1:])))
            g.clear()
            self.assertEqual(g.samples, [])
            self.assertEqual(g.timestamps, [])
        finally:
            g.deleteLater()

    def test_monotonic_defaults_and_truthful_axis(self):
        g = CpuGraph()
        try:
            with patch.object(ui_components.time, "monotonic", return_value=100.0):
                g.append(10)
            self.assertEqual(g.timestamps, [100.0])
            self.assertEqual(g.time_labels(), ("1 reading", "", "", "latest"))
            g.append(20, timestamp=100.25)
            self.assertEqual(g.time_labels(), ("span 0.25s", "−0.25s", "−0.125s", "latest"))
            g.gap()
            self.assertEqual(g.time_labels()[-1], "latest")
            g.resize(360, 200)
            g.show()
            g.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            ensure_app().processEvents()
            self.assertTrue(g.hasFocus())
            self.assertFalse(g.grab().isNull())
        finally:
            g.deleteLater()

    def test_zero_duration_points_and_native_focus_paint(self):
        app = ensure_app()
        old_style = app.style().objectName()
        app.setStyle("Fusion")
        g = CpuGraph()
        try:
            g.append(10, timestamp=100)
            self.assertEqual(g._time_fraction(100), 1.0)
            g.append(20, timestamp=100)
            self.assertEqual(g._time_fraction(100), 1.0)
            self.assertEqual(g.time_labels(), ("span 0s", "", "", "latest"))
            g.append(30, timestamp=101)
            self.assertEqual(g._time_fraction(100), 0.0)
            self.assertEqual(g._time_fraction(101), 1.0)
            g.resize(360, 200)
            g.show()
            app.processEvents()
            g.clearFocus()
            app.processEvents()
            self.assertFalse(g.hasFocus())
            unfocused = g.grab().toImage()
            g.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            app.processEvents()
            self.assertTrue(g.hasFocus())
            focused = g.grab().toImage()
            # The perimeter must visibly change under the native Fusion style.
            changed = sum(unfocused.pixel(x, y) != focused.pixel(x, y)
                          for y in range(5) for x in range(g.width()))
            self.assertGreater(changed, 20)
        finally:
            g.deleteLater()
            app.setStyle(old_style)

    def test_names_paint_accessible(self):
        g = CpuGraph()
        try:
            self.assertEqual(g.objectName(), "CpuGraph")
            self.assertTrue(g.accessibleName())
            self.assertGreaterEqual(g.minimumHeight(), 170)
            self.assertGreaterEqual(g.font().pointSizeF() if g.font().pointSizeF() > 0 else 9.0, 1.0)
            g.append(25, timestamp=time.time() - 60)
            g.append(75, timestamp=time.time())
            self.assertIn("75", g.accessibleDescription())
            self.assertIn(str(len(g.samples)), g.accessibleDescription())
            g.resize(360, 200)
            g.show()
            ensure_app().processEvents()
            pix = g.grab()
            self.assertFalse(pix.isNull())
            # Empty graph also paints.
            g.clear()
            ensure_app().processEvents()
            self.assertFalse(g.grab().isNull())
        finally:
            g.deleteLater()


class DetailTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_basics_and_missing(self):
        table = DetailTable(["A", "B"])
        try:
            self.assertIsInstance(table, QtWidgets.QTableWidget)
            self.assertEqual(table.columnCount(), 2)
            self.assertEqual(
                table.verticalScrollMode(),
                QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel,
            )
            self.assertEqual(
                table.editTriggers(),
                QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers,
            )
            self.assertGreaterEqual(table.verticalHeader().defaultSectionSize(), table.fontMetrics().height() + 12)
            table.set_rows([[None, float("nan")], ["x", float("inf")]])
            self.assertEqual(table.item(0, 0).text(), UNAVAILABLE)
            self.assertEqual(table.item(0, 1).text(), UNAVAILABLE)
            self.assertEqual(table.item(1, 1).text(), UNAVAILABLE)
            # No truncation of big lists.
            table.set_rows([["s%d" % i, "v"] for i in range(200)])
            self.assertEqual(table.rowCount(), 200)
        finally:
            table.deleteLater()

    def test_preserve_selection_scroll_and_changed_cells(self):
        table = DetailTable(["K", "V"])
        try:
            table.set_rows([["a", "1"], ["b", "2"], ["c", "3"]])
            table.selectRow(1)
            vbar = table.verticalScrollBar()
            table.set_rows([["a", "1"], ["b", "CHANGED"], ["c", "3"]])
            self.assertTrue(table.selectionModel().isRowSelected(1, QtCore.QModelIndex()))
            # Only changed cell gets a new text; unchanged items keep identity.
            self.assertEqual(table.item(0, 0).text(), "a")
            self.assertEqual(table.item(1, 1).text(), "CHANGED")
            self.assertGreaterEqual(vbar.maximum(), 0)
        finally:
            table.deleteLater()

    def test_generator_headers_multi_selection_and_font(self):
        table = DetailTable(name for name in ("K", "V"))
        try:
            table.set_rows([["a", "1"], ["b", "2"], ["c", "3"]])
            selection = table.selectionModel()
            flags = (QtCore.QItemSelectionModel.SelectionFlag.Select
                     | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            selection.select(table.model().index(0, 0), flags)
            selection.select(table.model().index(2, 0), flags)
            table.setCurrentCell(1, 0, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            table.set_rows([["a", "4"], ["b", "5"], ["c", "6"]])
            self.assertEqual({i.row() for i in selection.selectedRows()}, {0, 2})
            self.assertEqual(table.currentRow(), 1)
            self.assertEqual(table.copy_selected(), "K\tV\na\t4\nc\t6")
            table.set_rows([["c", "7"], ["b", "8"], ["a", "9"]])
            self.assertEqual(table.copy_selected(), "K\tV\nc\t7\na\t9")
            table.set_rows([["b", "8"], ["a", "9"]])
            self.assertEqual(table.copy_selected(), "K\tV\na\t9")
            table.setCurrentCell(0, 0, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            table.set_rows([["a", "10"]])
            self.assertEqual(table.currentRow(), -1)
            self.assertEqual(table.copy_selected(), "K\tV\na\t10")
            font = table.font()
            font.setPointSize(24)
            table.setFont(font)
            self.assertGreaterEqual(table.verticalHeader().defaultSectionSize(),
                                    table.fontMetrics().height() + 12)
            table.set_rows([["No sensors", ""], ["sensor", None]])
            self.assertEqual(table.item(0, 1).text(), "")
            self.assertEqual(table.item(1, 1).text(), UNAVAILABLE)
        finally:
            table.deleteLater()

    def test_filter_and_copy(self):
        table = DetailTable(["Name", "Value"])
        try:
            table.set_rows([["CPU", "42%"], ["Memory", "50%"], ["Disk", "20%"]])
            table.apply_filter("mem")
            self.assertTrue(table.isRowHidden(0))
            self.assertFalse(table.isRowHidden(1))
            self.assertTrue(table.isRowHidden(2))
            # Filter reapplied after set_rows.
            table.set_rows([["CPU", "42%"], ["Memory", "51%"]])
            self.assertTrue(table.isRowHidden(0))
            self.assertFalse(table.isRowHidden(1))
            self.assertEqual(table.filter_text, "mem")
            table.filter_text = ""
            self.assertFalse(table.isRowHidden(0))
            # Copy selected rows with headers, tab-separated.
            table.clearSelection()
            table.selectRow(0)
            text = table.copy_selected()
            self.assertIn("Name\tValue", text)
            self.assertIn("CPU\t42%", text)
            clip = QtWidgets.QApplication.clipboard()
            if clip is not None:
                self.assertEqual(clip.text(), text)
            # Case-insensitive across all cells.
            table.apply_filter("42%")
            self.assertFalse(table.isRowHidden(0))
            # Ctrl+C action exists and does not move focus.
            shortcuts = [a.shortcut().toString() for a in table.actions()]
            self.assertTrue(any("Ctrl+C" in s or "Copy" in s for s in shortcuts) or table.actions())
            focused_before = table.hasFocus()
            table.copy_selected()
            self.assertEqual(table.hasFocus(), focused_before)
        finally:
            table.deleteLater()


if __name__ == "__main__":
    unittest.main()
