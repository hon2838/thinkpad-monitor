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
        text = value.strip()
        return text if text else UNAVAILABLE
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
        self.setAccessibleDescription(self.format())

    @property
    def available(self):
        return self._available


class SummaryCard(QtWidgets.QFrame):
    """Title + large value + detail with an embedded compact UsageBar."""

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
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(4)

        self._title = QtWidgets.QLabel(str(title), self)
        self._title.setObjectName("SummaryCardTitle")
        self._title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        title_font = self._title.font()
        title_font.setPointSizeF(max(9.0, title_font.pointSizeF()))
        self._title.setFont(title_font)

        self._value = QtWidgets.QLabel(UNAVAILABLE, self)
        self._value.setObjectName("SummaryCardValue")
        self._value.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        value_font = self._value.font()
        base = value_font.pointSizeF() if value_font.pointSizeF() > 0 else 10.0
        value_font.setPointSizeF(base + 6.0)
        value_font.setBold(True)
        self._value.setFont(value_font)

        self._detail = QtWidgets.QLabel("", self)
        self._detail.setObjectName("SummaryCardDetail")
        self._detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._detail.setWordWrap(True)
        detail_font = self._detail.font()
        detail_font.setPointSizeF(max(9.0, detail_font.pointSizeF()))
        self._detail.setFont(detail_font)
        self._detail.setVisible(False)

        self.bar = UsageBar(self)
        self.bar.setObjectName("SummaryCardBar")
        self.bar.setMaximumHeight(14)

        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._detail)
        lay.addWidget(self.bar)

        self._card_title = str(title)
        self.setAccessibleName(str(title))
        self.setAccessibleDescription("%s: %s" % (self._card_title, UNAVAILABLE))

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
            moment = time.time()
        else:
            try:
                moment = float(timestamp)
            except (TypeError, ValueError):
                moment = time.time()
            if not math.isfinite(moment):
                moment = time.time()
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
            "Latest CPU load %.0f percent, %d readings in history"
            % (latest, count)
        )

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

            font = self.font()
            if font.pointSizeF() > 0 and font.pointSizeF() < 9.0:
                font.setPointSizeF(9.0)
            painter.setFont(font)
            metrics = QtGui.QFontMetrics(font)
            left = 52
            right = 10
            top = 8
            bottom = 26
            plot = QtCore.QRect(
                rect.left() + left,
                rect.top() + top,
                max(0, rect.width() - left - right),
                max(0, rect.height() - top - bottom),
            )
            if plot.width() < 10 or plot.height() < 10:
                return
            # Grid + percent labels (native palette only).
            painter.setPen(QtGui.QPen(mid, 1))
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
            painter.setPen(QtGui.QPen(mid, 1))
            painter.drawRect(plot)

            if not self._points:
                painter.setPen(text)
                painter.drawText(
                    plot, QtCore.Qt.AlignmentFlag.AlignCenter, "No samples yet"
                )
                return

            t_values = [t for t, _ in self._points]
            t_min, t_max = t_values[0], t_values[-1]
            if not math.isfinite(t_min) or not math.isfinite(t_max):
                t_max = t_min + 1.0
            if t_max <= t_min:
                t_max = t_min + 1.0
            span = t_max - t_min

            def to_point(moment, val):
                x = plot.left() + ((moment - t_min) / span) * plot.width()
                y = plot.bottom() - (val / 100.0) * plot.height()
                return QtCore.QPointF(x, y)

            segments: list[list[QtCore.QPointF]] = [[]]
            for index, (moment, val) in enumerate(self._points):
                if index in self._breaks and segments[-1]:
                    segments.append([])
                segments[-1].append(to_point(moment, val))
            segments = [s for s in segments if s]

            fill = QtGui.QColor(highlight)
            fill.setAlpha(70)
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
                    painter.setBrush(fill)
                    painter.drawPolygon(poly)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(highlight, 1.6))
            for seg in segments:
                if len(seg) == 1:
                    painter.drawEllipse(seg[0], 2.0, 2.0)
                    continue
                path = QtGui.QPainterPath()
                path.moveTo(seg[0])
                for point in seg[1:]:
                    path.lineTo(point)
                painter.drawPath(path)

            # Actual time axis: relative labels from stored timestamps.
            painter.setPen(text)
            span_label = "last %ds" % int(round(span)) if span < 3600 else "last %.1fh" % (span / 3600.0)
            painter.drawText(
                plot.left() + 4, plot.top() + metrics.ascent(), span_label
            )
            mid_t = t_min + span / 2.0
            labels = (
                ("-%ds" % int(round(t_max - t_min)), t_min, QtCore.Qt.AlignmentFlag.AlignLeft),
                ("-%ds" % int(round(t_max - mid_t)), mid_t, QtCore.Qt.AlignmentFlag.AlignCenter),
                ("now", t_max, QtCore.Qt.AlignmentFlag.AlignRight),
            )
            baseline = plot.bottom() + metrics.ascent() + 4
            for label, moment, _align in labels:
                x = plot.left() + ((moment - t_min) / span) * plot.width()
                painter.drawText(int(x) - 20, baseline - metrics.ascent(), 40, metrics.height(),
                                 QtCore.Qt.AlignmentFlag.AlignCenter, label)
        finally:
            painter.end()


class DetailTable(QtWidgets.QTableWidget):
    """Read-only table; preserves selection/scroll, filters, copies."""

    def __init__(self, headers, parent=None):
        super().__init__(0, len(list(headers)), parent)
        self.setObjectName("DetailTable")
        self._headers = list(headers)
        self.setHorizontalHeaderLabels(self._headers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
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
        self._filter_text = ""
        self._copy_action = QtGui.QAction("Copy", self)
        self._copy_action.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        self._copy_action.setShortcutContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self._copy_action.triggered.connect(self.copy_selected)
        self.addAction(self._copy_action)

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
        selected = {i.row() for i in self.selectionModel().selectedRows()}
        current = self.currentIndex()
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
            for row in sorted(selected):
                if 0 <= row < self.rowCount():
                    self.selectRow(row)
            if current.isValid():
                rover = min(current.row(), self.rowCount() - 1)
                if rover >= 0:
                    self.setCurrentCell(
                        rover,
                        min(current.column(), self.columnCount() - 1),
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
