"""Tests for newly implemented and improved UI components.

Covers:
- Truly responsive detail summary cards (SummaryCard & ResponsiveCardRow)
- Keyboard-accessible CollapsibleSection
- Honest chart and meter semantics (HistoryGraph dual-series gaps, FanMeterWidget, ThermalZoneBar, ThermalZoneGrid)
"""
import unittest

from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from test_desktop import ensure_app

from thinkpad_monitor.ui_components import (
    UNAVAILABLE,
    CollapsibleSection,
    FanMeterWidget,
    HistoryGraph,
    ResponsiveCardRow,
    SummaryCard,
    ThermalZoneBar,
    ThermalZoneGrid,
)


class SummaryCardResponsiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_load_average_wrapped_height_allocation_no_clipping(self):
        """At 14pt system font, load average text must get sufficient height and not clip."""
        app = ensure_app()
        prev_font = app.font()
        font_14 = QtGui.QFont(prev_font)
        font_14.setPointSize(14)
        app.setFont(font_14)
        try:
            card = SummaryCard("Load Average")
            card.set_value("0.50, 0.40, 0.30", "1 min · 5 min · 15 min")
            card.resize(190, 200)
            card.show()
            app.processEvents()

            fm = QtGui.QFontMetrics(card._value.font())
            needed_h = card._value.heightForWidth(card._value.width())
            # For 14pt font, 2 lines of value require >= 70px height
            self.assertGreaterEqual(card._value.height(), needed_h)
            self.assertGreaterEqual(card._value.height(), fm.lineSpacing())
            # Ensure text is not clipped: minimum height must accommodate wrapped text
            self.assertGreaterEqual(card._value.minimumHeight(), needed_h)
        finally:
            app.setFont(prev_font)
            card.deleteLater()



class ResponsiveCardRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_stacks_at_narrow_widths_and_expands_when_wide(self):
        app = ensure_app()
        c1 = SummaryCard("Processor Load")
        c1.set_value("15.2%", "2.40 GHz · 8 cores")
        c2 = SummaryCard("Load Average")
        c2.set_value("0.50, 0.40, 0.30", "1 min · 5 min · 15 min")

        row = ResponsiveCardRow(c1, c2)
        try:
            self.assertEqual(len(row.cards), 2)
            # When very wide (e.g. 1000px), row must be horizontal (not stacked)
            row.resize(1000, 300)
            row.reflow()
            app.processEvents()
            self.assertFalse(row.is_stacked)
            self.assertFalse(row.isStacked())

            # When narrow (e.g. 360px or 440px with 14pt font needed horizontal width ~450px), must stack
            row.resize(360, 400)
            row.reflow()
            app.processEvents()
            self.assertTrue(row.is_stacked)
            self.assertTrue(row.isStacked())

            # Both cards must still be valid and visible
            self.assertFalse(c1.isHidden())
            self.assertFalse(c2.isHidden())

            # Verify size hints and height-for-width
            self.assertTrue(row.hasHeightForWidth())
            h_narrow = row.heightForWidth(360)
            h_wide = row.heightForWidth(1000)
            self.assertGreater(h_narrow, h_wide)
        finally:
            row.deleteLater()

    def test_reflow_on_card_value_change(self):
        app = ensure_app()
        c1 = SummaryCard("Processor Load")
        c1.set_value("1%", "Idle")
        c2 = SummaryCard("Load Average")
        c2.set_value("0.1", "1 min")

        row = ResponsiveCardRow(c1, c2)
        try:
            row.resize(500, 300)
            row.reflow()
            app.processEvents()

            # Now update c2 with a much wider value
            c2.set_value("999.99, 888.88, 777.77, 666.66", "1 min · 5 min · 15 min · peak")
            app.processEvents()
            # If width is constrained, it triggers reflow and recalculates
            row.resize(400, 300)
            row.reflow()
            app.processEvents()
            self.assertTrue(row.is_stacked)
        finally:
            row.deleteLater()


class CollapsibleSectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_initially_collapsed_and_toggle(self):
        app = ensure_app()
        content = QtWidgets.QLabel("Detailed content here")
        section = CollapsibleSection("Logical cores", content, expanded=False)
        try:
            # Initially collapsed
            self.assertFalse(section.isExpanded())
            self.assertFalse(section.is_expanded())
            self.assertTrue(content.isHidden())
            # Content is kept alive and part of section
            self.assertIs(section.content_widget, content)

            # Check accessible state
            btn = section._toggle_button
            self.assertIn("collapsed", btn.accessibleDescription())
            self.assertFalse(btn.icon().isNull())
            self.assertIn("Logical cores", btn.text())

            # Test expanding
            toggled_events = []
            section.toggled.connect(lambda val: toggled_events.append(val))
            section.setExpanded(True)
            app.processEvents()

            self.assertTrue(section.isExpanded())
            self.assertTrue(section.is_expanded())
            self.assertFalse(content.isHidden())
            self.assertIn("expanded", btn.accessibleDescription())
            self.assertFalse(btn.icon().isNull())
            self.assertEqual(toggled_events, [True])

            # Toggle back to collapsed
            section.toggle()
            app.processEvents()
            self.assertFalse(section.isExpanded())
            self.assertTrue(content.isHidden())
            self.assertEqual(toggled_events, [True, False])
            QtTest.QTest.keyClick(btn, QtCore.Qt.Key.Key_Space)
            self.assertTrue(section.isExpanded())
            self.assertFalse(content.isHidden())
        finally:
            section.deleteLater()


class HistoryGraphHonestSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_dual_series_preserves_none_and_paints_gaps(self):
        """HistoryGraph must preserve None per channel and not convert to fake zero."""
        app = ensure_app()
        graph = HistoryGraph(
            limit=10,
            title="Network",
            mode="rate",
            series_count=2,
            series_labels=["Download", "Upload"],
        )
        try:
            # Append readings with partial missing data
            # Sample 0: down=1000, up=None (upload channel missing)
            graph.append(1000.0, None, timestamp=10.0)
            # Sample 1: down=2000, up=500
            graph.append(2000.0, 500.0, timestamp=11.0)
            # Sample 2: down=None, up=1500 (download channel missing)
            graph.append(None, 1500.0, timestamp=12.0)
            # Sample 3: down=0.0, up=0.0 (real zero!)
            graph.append(0.0, 0.0, timestamp=13.0)

            # Check that None was preserved in samples, NOT converted to 0.0!
            samples = graph.samples
            self.assertEqual(len(samples), 4)
            self.assertEqual(samples[0], (1000.0, None))
            self.assertEqual(samples[1], (2000.0, 500.0))
            self.assertEqual(samples[2], (None, 1500.0))
            self.assertEqual(samples[3], (0.0, 0.0))

            # Segments check:
            # Series 0 (Download): has points at t=10 (1000), t=11 (2000). At t=12 it is None (gap!). At t=13 it is 0.0.
            # So series 0 must have TWO segments: [(10, 1000), (11, 2000)] and [(13, 0.0)].
            segs_0 = graph.segments_for_series(0)
            self.assertEqual(len(segs_0), 2)
            self.assertEqual(len(segs_0[0]), 2)
            self.assertEqual(len(segs_0[1]), 1)
            self.assertEqual(segs_0[1][0][1], 0.0)

            # Series 1 (Upload): t=10 is None (gap!). t=11 (500), t=12 (1500), t=13 (0.0).
            # So series 1 must have ONE segment starting at t=11: [(11, 500), (12, 1500), (13, 0.0)].
            segs_1 = graph.segments_for_series(1)
            self.assertEqual(len(segs_1), 1)
            self.assertEqual(len(segs_1[0]), 3)

            # Paint event must render cleanly without exception
            graph.resize(360, 200)
            graph.show()
            app.processEvents()
            pix = graph.grab()
            self.assertFalse(pix.isNull())
        finally:
            graph.deleteLater()

    def test_missing_latest_displays_unavailable_in_accessibility_and_legend(self):
        graph = HistoryGraph(
            limit=5,
            title="Thermals",
            mode="temp",
            series_count=2,
            series_labels=["Package", "Core"],
        )
        try:
            # Package has 55.0, Core is missing (None)
            graph.append(55.0, None, timestamp=10.0)
            desc = graph.accessibleDescription()
            self.assertIn("55.0 °C", desc)
            self.assertIn(UNAVAILABLE, desc)
        finally:
            graph.deleteLater()


class ThermalZoneAndFanMetersHonestSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_app()

    def test_thermal_bar_no_critical_limit_does_not_assume_100c(self):
        """When critical limit is unavailable or invalid, bar is hidden and temperature is plain."""
        bar = ThermalZoneBar("CPU Temp")
        try:
            # Valid celsius, no critical limit provided
            bar.update_sensor("CPU Temp", 45.2, None)
            self.assertIn("45.2 °C", bar._temp_label.text())
            self.assertNotIn("crit", bar._temp_label.text())
            # Usage bar must be hidden (neutral representation, no fake 45% based on fake 100C)
            self.assertTrue(bar.bar.isHidden())

            # Invalid critical limit (string or negative) must not discard valid temperature
            bar.update_sensor("CPU Temp", 60.5, "corrupted-metadata")
            self.assertIn("60.5 °C", bar._temp_label.text())
            self.assertTrue(bar.bar.isHidden())

            bar.update_sensor("CPU Temp", 60.5, float('inf'))
            self.assertIn("60.5 °C", bar._temp_label.text())
            self.assertTrue(bar.bar.isHidden())

            # Valid critical limit shows the bar and crit label
            bar.update_sensor("CPU Temp", 75.0, 100.0)
            self.assertFalse(bar.bar.isHidden())
            self.assertEqual(bar.bar.value(), 75)
            self.assertIn("crit 100°C", bar._temp_label.text())
        finally:
            bar.deleteLater()

    def test_thermal_grid_discloses_12_sensor_cap(self):
        grid = ThermalZoneGrid()
        try:
            # Update with 16 sensors
            sensors = [
                {"name": f"temp_{i}", "label": f"Zone {i}", "celsius": 40.0 + i}
                for i in range(16)
            ]
            grid.update_sensors(sensors)
            self.assertEqual(len(grid._widgets), 12)
            self.assertFalse(grid._cap_label.isHidden())
            self.assertIn("Showing 12 of 16 sensors", grid._cap_label.text())

            # When <= 12, cap label is hidden
            grid.update_sensors(sensors[:8])
            self.assertEqual(len(grid._widgets), 8)
            self.assertTrue(grid._cap_label.isHidden())
        finally:
            grid.deleteLater()

    def test_fan_meter_does_not_assume_5500_rpm(self):
        """FanMeterWidget must not invent 5500 RPM max."""
        meter = FanMeterWidget("System Fan")
        try:
            # When max_rpm is not supplied, bar is hidden and numeric RPM is displayed plainly
            meter.update_fan("System Fan", 2400.0)
            self.assertIn("2400 RPM", meter._rpm_label.text())
            self.assertTrue(meter.bar.isHidden())

            # 0 RPM displays Off / 0 RPM
            meter.update_fan("System Fan", 0.0)
            self.assertIn("Off / 0 RPM", meter._rpm_label.text())
            self.assertTrue(meter.bar.isHidden())

            # When genuine max_rpm is supplied, bar is shown
            meter.update_fan("System Fan", 2500.0, max_rpm=5000.0)
            self.assertFalse(meter.bar.isHidden())
            self.assertEqual(meter.bar.value(), 50)
        finally:
            meter.deleteLater()


if __name__ == "__main__":
    unittest.main()
