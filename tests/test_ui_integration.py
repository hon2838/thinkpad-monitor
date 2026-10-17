"""End-to-end regressions for compact pages and labelled power readings."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtCore, QtGui
from thinkpad_monitor.desktop import MonitorWindow
from thinkpad_monitor.ui_components import CollapsibleSection, SummaryCard
from test_desktop import FakeCollector, ensure_app, make_sample, wait_for


class UiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = ensure_app()
        self.original_font = self.app.font()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.shutdown()
            window.close()
        self.app.setFont(self.original_font)
        self.app.processEvents()

    def window(self):
        window = MonitorWindow(FakeCollector(), interval=60)
        self.windows.append(window)
        window.toggle_pause()
        return window

    def test_power_domains_are_individual_and_selection_survives_reordering(self):
        window = self.window()
        window._on_sample(make_sample(power=[
            {'name': 'package-0', 'watts': 10}, {'name': 'core', 'watts': 4}]))
        self.assertEqual(window._power_draw_card.value_text, '10.00 W')
        self.assertEqual(window._power_graph.samples, [10.0])
        self.assertIn('package-0', window._power_graph.accessibleName())
        window._power_domain_combo.setCurrentIndex(1)
        self.assertEqual(window._power_draw_card.value_text, '4.00 W')
        self.assertEqual(window._power_graph.samples, [4.0])
        window._on_sample(make_sample(power=[
            {'name': 'core', 'watts': 0}, {'name': 'package-0', 'watts': 11}]))
        self.assertEqual(window._power_domain_combo.currentText(), 'core')
        self.assertEqual(window._power_draw_card.value_text, '0.00 W')
        self.assertEqual(window._power_graph.samples, [4.0, 0.0])
        window._on_sample(make_sample(power=[]))
        self.assertEqual(window._power_draw_card.value_text, 'Unavailable')
        self.assertEqual(window._power_graph.samples, [])
        self.assertFalse(window._power_domain_combo.isEnabled())

    def test_missing_power_readings_do_not_become_zero_or_nan(self):
        window = self.window()
        for value in (None, float('nan'), float('inf')):
            window._on_sample(make_sample(power=[{'name': 'package-0', 'watts': value}]))
            self.assertEqual(window._power_draw_card.value_text, 'Unavailable')
            self.assertEqual(window._power_graph.samples, [])

    def test_filter_expands_details_and_collapsing_preserves_rows_and_selection(self):
        window = self.window()
        window._on_sample(make_sample())
        window.resize(1100, 800)
        window.show()
        window.activateWindow()
        window._select_page(1)
        self.app.processEvents()
        table = window._cpu_table
        section = table.parentWidget()
        while not isinstance(section, CollapsibleSection):
            section = section.parentWidget()
        self.assertFalse(section.isExpanded())
        window._focus_filter()
        self.app.processEvents()
        self.assertTrue(section.isExpanded())
        self.assertTrue(table.filter_edit.hasFocus())
        def filter_is_visible():
            viewport = window._tabs.currentWidget().viewport()
            position = table.filter_edit.mapTo(viewport, QtCore.QPoint(0, 0))
            return position.y() >= 0 and position.y() + table.filter_edit.height() <= viewport.height()
        self.assertTrue(wait_for(filter_is_visible, app=self.app), "focused filter stayed outside the viewport")
        table.selectRow(0)
        copied = table.copy_selected()
        count = table.rowCount()
        section.setExpanded(False)
        window._on_sample(make_sample())
        self.assertEqual(table.rowCount(), count)
        section.setExpanded(True)
        self.assertEqual(table.copy_selected(), copied)

    def test_compact_detail_values_remain_readable_with_large_fonts(self):
        font = QtGui.QFont(self.original_font)
        font.setPointSize(14)
        self.app.setFont(font)
        window = self.window()
        window._on_sample(make_sample())
        window.show()
        for width in (360, 480, 600):
            window.resize(width, 640)
            for page in (1, 2, 3, 5, 6, 7, 8):
                window._select_page(page)
                self.app.processEvents()
                self.app.processEvents()
                for card in window._tabs.currentWidget().findChildren(SummaryCard):
                    for label in (card._value, card._detail):
                        if not label.isVisible() or not label.text():
                            continue
                        needed = label.fontMetrics().boundingRect(
                            QtCore.QRect(0, 0, label.contentsRect().width(), 2000),
                            QtCore.Qt.TextFlag.TextWordWrap, label.text()).height()
                        self.assertGreaterEqual(label.contentsRect().height(), needed,
                            (width, page, label.text(), label.contentsRect().size(), needed))

    def test_laptop_thermals_prioritizes_main_history_and_keeps_details_available(self):
        window = self.window()
        window._on_sample(make_sample())
        window.resize(1366, 768)
        window.show()
        window._select_page(6)
        self.app.processEvents()
        self.assertTrue(window._therm_graph.isVisible())
        self.assertFalse(window._fan_graph.isVisible())
        self.assertFalse(window._temp_table.isVisible())
        self.assertEqual(window._temp_table.rowCount(), 1)
        self.assertLessEqual(window._therm_graph.height(), 230)
        self.assertLess(window._tabs.currentWidget().verticalScrollBar().maximum(), 400)
