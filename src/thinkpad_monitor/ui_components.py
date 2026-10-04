"""Native PySide6 widgets for the desktop dashboard (no hardware/network).

Root owns ``desktop.py`` (window, sampling, status). This module only provides
reusable widgets with stable public APIs used by existing desktop tests.
"""
from __future__ import annotations

import math
import time

from PySide6 import QtCore, QtGui, QtWidgets

__all__ = [
    "CPU_HISTORY_LIMIT",
    "UNAVAILABLE",
    "SummaryCard",
    "UsageBar",
    "CpuGraph",
    "DetailTable",
]

CPU_HISTORY_LIMIT = 180
UNAVAILABLE = "Unavailable"


def _is_missing(value) -> bool:
    """True for None or non-finite numbers (nan/inf)."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        try:
            return not math.isfinite(float(value))
        except (TypeError, ValueError):
            return True
    return False


def _coerce_percent(value):
    """Return clamped 0..100 float or None when missing/non-finite."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(100.0, number))


def _cell_text(value) -> str:
    if _is_missing(value):
        return UNAVAILABLE
    if isinstance(value, str):
        return value.strip()
    return str(value)


class UsageBar(QtWidgets.QProgressBar):
    """Progress bar showing a percentage or Unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UsageBar")
        self.setAccessibleName("Usage level")
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(True)
        self._available = False
        self.setFormat(UNAVAILABLE)
        self.setAccessibleDescription(UNAVAILABLE)

    def set_usage(self, percent, text=None):
        value = _coerce_percent(percent)
        if value is None:
            self._available = False
            self.setValue(0)
            self.setFormat(UNAVAILABLE)
            self.setAccessibleDescription(UNAVAILABLE)
            return
        self._available = True
        self.setValue(int(round(value)))
        self.setFormat(text if text else "%p%")
        self.setAccessibleDescription(text if text else f"{value:.0f} percent")

    @property
    def available(self):
        return self._available


class SummaryCard(QtWidgets.QFrame):
    """Title + large value + detail with an embedded compact UsageBar."""

    _ICON_SIZE = 20

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("SummaryCard")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        # Expanding horizontally, content-sized vertically; never clip text.
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        lay.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self._icon_label = QtWidgets.QLabel(self)
        self._icon_label.setObjectName("SummaryCardIcon")
        self._icon_label.setFixedSize(self._ICON_SIZE, self._ICON_SIZE)
        self._icon_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self._icon_label.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        # Decorative: excluded from screen readers.
        self._icon_label.setAccessibleName("")
        self._icon_label.setAccessibleDescription("")
        self._icon_label.setVisible(False)
        self._icon: QtGui.QIcon | None = None

        self._title = QtWidgets.QLabel(str(title), self)
        self._title.setObjectName("SummaryCardTitle")
        self._title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._title.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        header.addWidget(self._icon_label, 0)
        header.addWidget(self._title, 1)
        lay.addLayout(header)

        self._value = QtWidgets.QLabel(UNAVAILABLE, self)
        self._value.setObjectName("SummaryCardValue")
        self._value.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._detail = QtWidgets.QLabel("", self)
        self._detail.setObjectName("SummaryCardDetail")
        self._detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._detail.setVisible(False)

        self.bar = UsageBar(self)
        self.bar.setObjectName("SummaryCardBar")
        self.bar.setMaximumHeight(14)

        lay.addWidget(self._value)
        lay.addWidget(self._detail)
        lay.addWidget(self.bar)

        self._card_title = str(title)
        self.setAccessibleName(str(title))
        self.setAccessibleDescription("%s: %s" % (self._card_title, UNAVAILABLE))
        self._apply_card_style()

    def set_icon(self, icon):
        """Show a decorative 20px icon in the header.

        Accepts a QIcon (or None to clear). The icon is purely
        decorative and hidden from accessibility tools. No external
        module is imported; any QIcon may be supplied.
        """
        if icon is None:
            self._icon = None
            self._icon_label.clear()
            self._icon_label.setVisible(False)
            return
        if not isinstance(icon, QtGui.QIcon):
            raise TypeError("icon must be a QIcon or None")
        if icon.isNull():
            self._icon = None
            self._icon_label.clear()
            self._icon_label.setVisible(False)
            return
        self._icon = icon
        self._refresh_icon_pixmap()
        self._icon_label.setVisible(True)

    def _refresh_icon_pixmap(self):
        if self._icon is None:
            return
        ratio = self.devicePixelRatioF()
        physical_size = round(self._ICON_SIZE * ratio)
        pm = self._icon.pixmap(
            QtCore.QSize(physical_size, physical_size),
            1.0,
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.Off,
        )
        if pm.isNull():
            self._icon_label.clear()
            self._icon_label.setVisible(False)
            return
        pm.setDevicePixelRatio(ratio)
        self._icon_label.setPixmap(pm)
        self._icon_label.setFixedSize(self._ICON_SIZE, self._ICON_SIZE)

    def _secondary_color(self) -> QtGui.QColor:
        # Read the window palette: stylesheet-resolved child palettes can
        # retain an earlier theme until Qt finishes propagating a change.
        pal = self.window().palette()
        foreground = pal.color(QtGui.QPalette.ColorRole.Text)
        background = pal.color(QtGui.QPalette.ColorRole.Base)
        muted = pal.color(QtGui.QPalette.ColorRole.PlaceholderText)
        # Placeholder colours often include transparency. Compose against
        # the actual card surface and retain readable body-text contrast.
        alpha = muted.alphaF()
        muted = QtGui.QColor(*(round(alpha * channel(muted) + (1-alpha) * channel(background))
                              for channel in (QtGui.QColor.red, QtGui.QColor.green, QtGui.QColor.blue)))
        def luminance(color):
            channels = [channel(color) / 255 for channel in
                        (QtGui.QColor.red, QtGui.QColor.green, QtGui.QColor.blue)]
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
            return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
        first, second = sorted((luminance(muted), luminance(background)))
        if (second + 0.05) / (first + 0.05) >= 4.5:
            return muted
        softened = QtGui.QColor(*(round(0.75 * channel(foreground) + 0.25 * channel(background))
                                  for channel in (QtGui.QColor.red, QtGui.QColor.green, QtGui.QColor.blue)))
        first, second = sorted((luminance(softened), luminance(background)))
        return softened if (second + 0.05) / (first + 0.05) >= 4.5 else foreground

    def _apply_card_style(self):
        base = self.font().pointSizeF()
        if not base or base <= 0:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                base = app.font().pointSizeF()
        if not base or base <= 0:
            base = 10.0
        title_font = QtGui.QFont(self.font())
        title_font.setPointSizeF(max(9.0, base))
        title_font.setBold(False)
        self._title.setFont(title_font)
        value_font = QtGui.QFont(self.font())
        value_font.setPointSizeF(base + 8.0)
        value_font.setBold(True)
        self._value.setFont(value_font)
        detail_font = QtGui.QFont(self.font())
        detail_font.setPointSizeF(max(9.0, base))
        self._detail.setFont(detail_font)
        # Muted secondary text from the native palette (readable contrast,
        # high-contrast safe). Value keeps the default Text color.
        secondary = self._secondary_color()
        for label in (self._title, self._detail):
            pal = QtGui.QPalette(self.window().palette())
            pal.setColor(QtGui.QPalette.ColorRole.WindowText, secondary)
            pal.setColor(QtGui.QPalette.ColorRole.Text, secondary)
            label.setPalette(pal)
        # Reserve space for a caption so cards align, but allow growth
        # for wrapped text and enlarged fonts.
        metrics = QtGui.QFontMetrics(detail_font)
        self._detail.setMinimumHeight(metrics.lineSpacing() + 2)
        self._refresh_icon_pixmap()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.Type.FontChange,
            QtCore.QEvent.Type.PaletteChange,
            QtCore.QEvent.Type.StyleChange,
            QtCore.QEvent.Type.ApplicationPaletteChange,
            QtCore.QEvent.Type.ApplicationFontChange,
        ):
            self._apply_card_style()

    def set_value(self, value, detail=None):
        if _is_missing(value):
            shown = UNAVAILABLE
        elif isinstance(value, str):
            shown = value if value.strip() else UNAVAILABLE
        else:
            shown = str(value)
        self._value.setText(shown)
        if detail is None:
            self._detail.setText("")
            self._detail.setVisible(False)
            detail_text = ""
        else:
            if _is_missing(detail):
                detail_shown = UNAVAILABLE
            else:
                detail_shown = str(detail)
                if not detail_shown.strip():
                    self._detail.setText("")
                    self._detail.setVisible(False)
                    self._refresh_accessible(shown, "")
                    return
            self._detail.setText(detail_shown)
            self._detail.setVisible(True)
            detail_text = detail_shown
        self._refresh_accessible(shown, detail_text)

    def _refresh_accessible(self, value_text, detail_text):
        desc = "%s: %s" % (self._card_title, value_text)
        if detail_text:
            desc += " (%s)" % detail_text
        self.setAccessibleDescription(desc)
        self._value.setAccessibleName("%s value" % self._card_title)
        self._value.setAccessibleDescription(value_text)

    @property
    def value_text(self):
        return self._value.text()


class CpuGraph(QtWidgets.QWidget):
    """History graph with real timestamps; gaps break the trace."""

    def __init__(self, parent=None, limit=CPU_HISTORY_LIMIT):
        super().__init__(parent)
        self.setObjectName("CpuGraph")
        self.setAccessibleName("CPU usage history graph")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._limit = max(2, int(limit))
        self._points: list[tuple[float, float]] = []
        self._breaks: set[int] = set()
        self._pending_break = False
        self.setMinimumHeight(170)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setAccessibleDescription("No CPU history yet")

    def append(self, percent, timestamp=None):
        value = _coerce_percent(percent)
        if value is None:
            # Missing/non-finite: skip and break the next segment.
            if self._points:
                self._pending_break = True
            return
        if timestamp is None:
            moment = time.monotonic()
        else:
            try:
                moment = float(timestamp)
            except (TypeError, ValueError):
                moment = time.monotonic()
            if not math.isfinite(moment):
                moment = time.monotonic()
        if self._pending_break and self._points:
            self._breaks.add(len(self._points))
        self._pending_break = False
        self._points.append((moment, value))
        if len(self._points) > self._limit:
            excess = len(self._points) - self._limit
            del self._points[:excess]
            kept = {b - excess for b in self._breaks if b - excess > 0}
            self._breaks = kept
        self._refresh_accessible()
        self.update()

    def gap(self):
        """Break the trace; next known reading starts a new segment."""
        if self._points:
            self._pending_break = True
        self.update()

    def clear(self):
        self._points = []
        self._breaks = set()
        self._pending_break = False
        self.setAccessibleDescription("No CPU history yet")
        self.update()

    @property
    def samples(self):
        return [v for _, v in self._points]

    @property
    def timestamps(self):
        return [t for t, _ in self._points]

    def _refresh_accessible(self):
        count = len(self._points)
        if not count:
            self.setAccessibleDescription("No CPU history yet")
            return
        latest = self._points[-1][1]
        self.setAccessibleDescription(
            "Latest recorded CPU load %.0f percent, %d readings in history, %s"
            % (latest, count, self.time_labels()[0])
        )

    @staticmethod
    def _duration_label(seconds):
        if seconds == 0:
            return "0s"
        if seconds < 1:
            return f"{seconds:.3g}s"
        if seconds < 60:
            return f"{seconds:.1f}s".replace(".0s", "s")
        if seconds < 3600:
            return f"{seconds / 60:.1f}m"
        return f"{seconds / 3600:.1f}h"

    def time_labels(self):
        """Relative to the latest stored sample, including paused history."""
        if len(self._points) < 2:
            return "1 reading", "", "", "latest"
        span = max(0.0, self._points[-1][0] - self._points[0][0])
        return (f"span {self._duration_label(span)}",
                f"−{self._duration_label(span)}" if span else "",
                f"−{self._duration_label(span / 2)}" if span else "",
                "latest")

    def _time_fraction(self, moment):
        """Position within stored history; zero-duration readings are latest."""
        start, end = self._points[0][0], self._points[-1][0]
        if end <= start:
            return 1.0
        return max(0.0, min(1.0, (moment - start) / (end - start)))

    def focusInEvent(self, event):  # noqa: N802
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):  # noqa: N802
        super().focusOutEvent(event)
        self.update()

    def sizeHint(self):  # noqa: N802
        return QtCore.QSize(360, 190)

    def paintEvent(self, event):  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        try:
            rect = self.rect()
            pal = self.palette()
            base = pal.color(QtGui.QPalette.ColorRole.Base)
            text = pal.color(QtGui.QPalette.ColorRole.Text)
            mid = pal.color(QtGui.QPalette.ColorRole.Mid)
            highlight = pal.color(QtGui.QPalette.ColorRole.Highlight)
            painter.fillRect(rect, base)
            if self.hasFocus():
                option = QtWidgets.QStyleOptionFocusRect()
                option.initFrom(self)
                option.state |= (QtWidgets.QStyle.StateFlag.State_KeyboardFocusChange
                                 | QtWidgets.QStyle.StateFlag.State_Item)
                option.rect = rect.adjusted(2, 2, -2, -2)
                option.backgroundColor = base
                self.style().drawPrimitive(
                    QtWidgets.QStyle.PrimitiveElement.PE_FrameFocusRect,
                    option, painter, self,
                )

            font = self.font()
            if font.pointSizeF() > 0 and font.pointSizeF() < 9.0:
                font.setPointSizeF(9.0)
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)
            left = metrics.horizontalAdvance("100%") + 14
            right = 10
            top = 8
            bottom = metrics.height() + 10
            plot = QtCore.QRect(
                rect.left() + left,
                rect.top() + top,
                max(0, rect.width() - left - right),
                max(0, rect.height() - top - bottom),
            )
            if plot.width() < 10 or plot.height() < 10:
                return
            # Grid + percent labels (native palette only, lighter grid).
            grid_color = QtGui.QColor(mid)
            grid_color.setAlpha(120)
            grid_pen = QtGui.QPen(grid_color, 1)
            grid_pen.setCosmetic(True)
            painter.setPen(grid_pen)
            for pct in (0, 50, 100):
                y = plot.bottom() - int(round(plot.height() * (pct / 100.0)))
                painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(text)
            painter.drawText(
                4, plot.top() + metrics.ascent(), "100%"
            )
            painter.drawText(
                4, plot.center().y() + metrics.ascent() // 2, "50%"
            )
            painter.drawText(4, plot.bottom(), "0%")
            # No full plot border: the 0% grid line acts as the baseline.

            if not self._points:
                painter.setPen(text)
                painter.drawText(
                    plot, QtCore.Qt.AlignmentFlag.AlignCenter, "No samples yet"
                )
                return

            def to_point(moment, val):
                x = plot.left() + self._time_fraction(moment) * (plot.width() - 1)
                y = plot.bottom() - (val / 100.0) * (plot.height() - 1)
                return QtCore.QPointF(x, y)

            segments: list[list[QtCore.QPointF]] = [[]]
            for index, (moment, val) in enumerate(self._points):
                if index in self._breaks and segments[-1]:
                    segments.append([])
                segments[-1].append(to_point(moment, val))
            segments = [s for s in segments if s]

            # Subtle vertical area gradient derived from Highlight.
            top_fill = QtGui.QColor(highlight)
            top_fill.setAlpha(72)
            bottom_fill = QtGui.QColor(highlight)
            bottom_fill.setAlpha(10)
            gradient = QtGui.QLinearGradient(0, plot.top(), 0, plot.bottom())
            gradient.setColorAt(0.0, top_fill)
            gradient.setColorAt(1.0, bottom_fill)
            for seg in segments:
                if len(seg) >= 2:
                    poly = QtGui.QPolygonF(seg)
                    poly.append(
                        QtCore.QPointF(seg[-1].x(), plot.bottom())
                    )
                    poly.append(
                        QtCore.QPointF(seg[0].x(), plot.bottom())
                    )
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(gradient)
                    painter.drawPolygon(poly)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            trace_pen = QtGui.QPen(highlight, 2.0)
            trace_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            trace_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            trace_pen.setCosmetic(False)
            painter.setPen(trace_pen)
            for seg in segments:
                if len(seg) == 1:
                    painter.drawEllipse(seg[0], 2.0, 2.0)
                    continue
                path = QtGui.QPainterPath()
                path.moveTo(seg[0])
                for point in seg[1:]:
                    path.lineTo(point)
                painter.drawPath(path)
            # Latest-sample dot with a Base outline for light/dark contrast.
            latest_point = segments[-1][-1] if segments else None
            if latest_point is not None:
                painter.setPen(QtGui.QPen(base, 1.5))
                painter.setBrush(highlight)
                painter.drawEllipse(latest_point, 3.5, 3.5)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

            # Actual time axis: relative labels from stored timestamps.
            painter.setPen(text)
            span_label, left_label, middle_label, right_label = self.time_labels()
            painter.drawText(
                plot.left() + 4, plot.top() + metrics.ascent(), span_label
            )
            axis = QtCore.QRect(plot.left(), plot.bottom() + 4,
                                plot.width(), metrics.height())
            painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignLeft, left_label)
            painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignRight, right_label)
            occupied = metrics.horizontalAdvance(left_label + right_label + middle_label) + 30
            if plot.width() >= occupied:
                painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignHCenter, middle_label)
        finally:
            painter.end()


class DetailTable(QtWidgets.QTableWidget):
    """Read-only table; preserves selection/scroll, filters, copies."""

    def __init__(self, headers, parent=None):
        headers = list(headers)
        super().__init__(0, len(headers), parent)
        self.setObjectName("DetailTable")
        self._headers = headers
        self.setHorizontalHeaderLabels(self._headers)
        self.verticalHeader().setVisible(False)
        self._update_row_height()
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setAlternatingRowColors(True)
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setHorizontalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        header = self.horizontalHeader()
        header.setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        # Native styling only: spacing via padding, no fixed colours, so
        # light/dark/high-contrast palettes keep working dynamically.
        self.setStyleSheet(
            "QTableWidget::item { padding: 4px 8px; }"
            " QHeaderView::section { padding: 7px 10px; }"
        )
        self._filter_text = ""
        self._copy_action = QtGui.QAction("Copy", self)
        self._copy_action.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        self._copy_action.setShortcutContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._copy_action.triggered.connect(self.copy_selected)
        self.addAction(self._copy_action)

    def _update_row_height(self):
        height = self.fontMetrics().height()
        self.verticalHeader().setDefaultSectionSize(max(34, height + 14))
        self.horizontalHeader().setMinimumHeight(height + 16)

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.FontChange, QtCore.QEvent.Type.StyleChange,
                            QtCore.QEvent.Type.ApplicationFontChange):
            self._update_row_height()

    @property
    def filter_text(self):
        return self._filter_text

    @filter_text.setter
    def filter_text(self, value):
        self.apply_filter(value)

    def apply_filter(self, text):
        self._filter_text = "" if text is None else str(text)
        needle = self._filter_text.casefold()
        for row in range(self.rowCount()):
            if not needle:
                self.setRowHidden(row, False)
                continue
            match = False
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item is not None and needle in item.text().casefold():
                    match = True
                    break
            self.setRowHidden(row, not match)

    def set_rows(self, rows):
        safe = [list(r) for r in rows]
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        vpos, hpos = vbar.value(), hbar.value()
        # First column is the displayed device/metric identity. Occurrence
        # numbers distinguish duplicate names without moving selection to a
        # different named device when telemetry reorders or removes rows.
        def row_keys(values):
            counts = {}
            result = []
            for value in values:
                count = counts.get(value, 0)
                result.append((value, count))
                counts[value] = count + 1
            return result

        old_keys = row_keys([
            self.item(row, 0).text() if self.item(row, 0) else ""
            for row in range(self.rowCount())
        ])
        selected = {old_keys[i.row()] for i in self.selectionModel().selectedRows()}
        current = self.currentIndex()
        current_key = old_keys[current.row()] if current.isValid() else None
        new_keys = row_keys([_cell_text(row[0]) if row else "" for row in safe])
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(len(safe))
            for row, data in enumerate(safe):
                for col in range(self.columnCount()):
                    raw = data[col] if col < len(data) else ""
                    text = _cell_text(raw)
                    item = self.item(row, col)
                    if item is None:
                        item = QtWidgets.QTableWidgetItem(text)
                        item.setFlags(
                            item.flags()
                            & ~QtCore.Qt.ItemFlag.ItemIsEditable
                        )
                        item.setToolTip(text)
                        self.setItem(row, col, item)
                    else:
                        if item.text() != text:
                            item.setText(text)
                        if item.toolTip() != text:
                            item.setToolTip(text)
            # Drop stale rows' selection; restore what still exists.
            self.selectionModel().clearSelection()
            for row, key in enumerate(new_keys):
                if key in selected:
                    self.selectionModel().select(
                        self.model().index(row, 0),
                        QtCore.QItemSelectionModel.SelectionFlag.Select
                        | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                    )
            if current_key in new_keys:
                rover = new_keys.index(current_key)
                if rover >= 0:
                    self.setCurrentCell(
                        rover,
                        min(current.column(), self.columnCount() - 1),
                        QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
                    )
            else:
                self.selectionModel().setCurrentIndex(
                    QtCore.QModelIndex(),
                    QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
                )
            self.apply_filter(self._filter_text)
            vbar.setValue(vpos)
            hbar.setValue(hpos)
        finally:
            self.setUpdatesEnabled(True)

    def copy_selected(self, _checked=False):
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        if not rows:
            # Fall back to rows with any selected cell.
            rows = sorted({i.row() for i in self.selectedItems()})
        lines = ["\t".join(self._headers)]
        for row in rows:
            if self.isRowHidden(row):
                continue
            cells = []
            for col in range(self.columnCount()):
                item = self.item(row, col)
                cells.append(item.text() if item is not None else "")
            lines.append("\t".join(cells))
        text = "\n".join(lines) if len(lines) > 1 else ""
        if text:
            clipboard = QtWidgets.QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
        return text
