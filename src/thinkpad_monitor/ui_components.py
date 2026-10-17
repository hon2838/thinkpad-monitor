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
    "HistoryGraph",
    "CpuGraph",
    "CoreBarWidget",
    "PerCoreGrid",
    "BatteryPackCard",
    "PowerSupplyCard",
    "ThermalZoneBar",
    "ThermalZoneGrid",
    "FanMeterWidget",
    "FanSpeedGrid",
    "DetailTable",
    "ResponsiveCardRow",
    "CollapsibleSection",
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


def _coerce_rate(value):
    """Return non-negative float or None when missing/non-finite."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def _coerce_float(value):
    """Return float or None when missing/non-finite."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _format_rate_unit(v):
    if v is None:
        return UNAVAILABLE
    try:
        n = float(v)
    except (TypeError, ValueError):
        return UNAVAILABLE
    for u in ("B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s"):
        if abs(n) < 1024.0 or u == "TiB/s":
            return "%d B/s" % int(n) if u == "B/s" else "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f TiB/s" % n


def _secondary_graph_color(primary: QtGui.QColor, base: QtGui.QColor) -> QtGui.QColor:
    h, s, v, a = primary.getHsv()
    if s < 30:
        return QtGui.QColor(primary).lighter(150) if v < 150 else QtGui.QColor(primary).darker(150)
    new_h = (h + 130) % 360
    return QtGui.QColor.fromHsv(new_h, max(140, s), v, a)


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
            self.recalculate_height()

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
                    self.recalculate_height()
                    if self.parentWidget() is not None and hasattr(self.parentWidget(), "reflow"):
                        self.parentWidget().reflow()
                    return
            self._detail.setText(detail_shown)
            self._detail.setVisible(True)
            detail_text = detail_shown
        self._refresh_accessible(shown, detail_text)
        self.recalculate_height()
        if self.parentWidget() is not None and hasattr(self.parentWidget(), "reflow"):
            self.parentWidget().reflow()

    def natural_width(self) -> int:
        """Width needed to show title, value, and detail without awkward wrapping."""
        fm_val = QtGui.QFontMetrics(self._value.font())
        w_val = fm_val.horizontalAdvance(self._value.text()) if self._value.text() else 0
        fm_title = QtGui.QFontMetrics(self._title.font())
        w_title = fm_title.horizontalAdvance(self._title.text()) + (self._ICON_SIZE + 8 if self._icon else 0)
        w_det = 0
        if self._detail.isVisible() and self._detail.text():
            fm_det = QtGui.QFontMetrics(self._detail.font())
            w_det = fm_det.horizontalAdvance(self._detail.text())
        margins = self.layout().contentsMargins() if self.layout() else None
        hm = (margins.left() + margins.right()) if margins else 32
        base = self.font().pointSizeF() or 10.0
        return max(int(round(base * 16)), max(w_val, w_title, w_det) + hm + 16)

    def _calculate_needed_height(self, width: int) -> int:
        margins = self.layout().contentsMargins() if self.layout() else None
        hm = (margins.left() + margins.right()) if margins else 32
        vm = (margins.top() + margins.bottom()) if margins else 28
        inner_w = max(20, width - hm)

        title_h = self._title.heightForWidth(inner_w - (self._ICON_SIZE + 6 if self._icon else 0))
        h = max(self._ICON_SIZE if self._icon else 0, title_h)
        spacing = self.layout().spacing() if self.layout() else 6

        if not self._value.isHidden() and self._value.text():
            val_h = self._value.heightForWidth(inner_w)
            h += val_h + spacing

        if not self._detail.isHidden() and self._detail.text():
            det_h = self._detail.heightForWidth(inner_w)
            h += det_h + spacing

        if not self.bar.isHidden() or self.bar.sizePolicy().retainSizeWhenHidden():
            h += self.bar.height() + spacing

        return h + vm

    def recalculate_height(self, width: int | None = None):
        """Update label minimum heights based on allocated or available width."""
        w = width if (width is not None and width > 0) else self.width()
        margins = self.layout().contentsMargins() if self.layout() else None
        hm = (margins.left() + margins.right()) if margins else 32
        inner_w = max(20, w - hm)

        if not self._value.isHidden() and self._value.text():
            val_h = self._value.heightForWidth(inner_w)
            fm = QtGui.QFontMetrics(self._value.font())
            self._value.setMinimumHeight(max(fm.lineSpacing(), val_h))

        if not self._detail.isHidden() and self._detail.text():
            det_h = self._detail.heightForWidth(inner_w)
            fm = QtGui.QFontMetrics(self._detail.font())
            self._detail.setMinimumHeight(max(fm.lineSpacing() + 2, det_h))

        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._calculate_needed_height(width)

    def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802
        base = self.font().pointSizeF() or 10.0
        fm_val = QtGui.QFontMetrics(self._value.font())
        tokens = self._value.text().split() if self._value.text() else []
        max_token_w = max((fm_val.horizontalAdvance(t) for t in tokens), default=0)
        margins = self.layout().contentsMargins() if self.layout() else None
        hm = (margins.left() + margins.right()) if margins else 32
        min_w = max(140, int(round(base * 10)), max_token_w + hm + 8)
        return QtCore.QSize(min_w, self._calculate_needed_height(min_w))

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        w = max(200, self.natural_width())
        return QtCore.QSize(w, self._calculate_needed_height(w))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.recalculate_height(event.size().width())

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


class ResponsiveCardRow(QtWidgets.QWidget):
    """Container for detail summary cards that stacks vertically when available

    width or card contents require it, and lays out horizontally when there is
    sufficient room.
    """

    def __init__(self, card1: SummaryCard, card2: SummaryCard, parent=None, spacing: int = 14):
        super().__init__(parent)
        self.setObjectName("responsiveCardRow")
        self._cards = [card1, card2]
        self._spacing = max(0, int(spacing))
        self._stacked = False

        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(self._spacing)

        for card in self._cards:
            card.setParent(self)

        self._apply_layout(force=True)

    @property
    def cards(self) -> list[SummaryCard]:
        return list(self._cards)

    @property
    def is_stacked(self) -> bool:
        return self._stacked

    def isStacked(self) -> bool:
        return self._stacked

    def _needed_horizontal_width(self) -> int:
        return sum(card.natural_width() for card in self._cards) + self._spacing

    def reflow(self):
        w = self.width()
        if w <= 0 and self.parentWidget():
            w = self.parentWidget().width()
        if w <= 0:
            return

        needed = self._needed_horizontal_width()
        should_stack = (w < needed)

        if should_stack != self._stacked:
            self._stacked = should_stack
            self._apply_layout()

        card_w = w if self._stacked else max(50, (w - self._spacing) // 2)
        for card in self._cards:
            card.recalculate_height(card_w)
        self.updateGeometry()

    def _apply_layout(self, force=False):
        while self._grid.count():
            self._grid.takeAt(0)

        if self._stacked:
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
            for idx, card in enumerate(self._cards):
                self._grid.addWidget(card, idx, 0)
        else:
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
            for idx, card in enumerate(self._cards):
                self._grid.addWidget(card, 0, idx)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.reflow()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.Type.FontChange,
            QtCore.QEvent.Type.ApplicationFontChange,
            QtCore.QEvent.Type.StyleChange,
        ):
            self.reflow()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        needed = self._needed_horizontal_width()
        if width < needed:
            return sum(c.heightForWidth(width) for c in self._cards) + self._spacing
        else:
            w_each = max(50, (width - self._spacing) // 2)
            return max(c.heightForWidth(w_each) for c in self._cards)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        needed = self._needed_horizontal_width()
        w = self.width() if self.width() > 0 else needed
        return QtCore.QSize(needed, self.heightForWidth(w))

    def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802
        min_card_w = max(c.minimumSizeHint().width() for c in self._cards)
        return QtCore.QSize(min_card_w, self.heightForWidth(min_card_w))



class HistoryGraph(QtWidgets.QWidget):
    """Multi-series history graph supporting percent, rate, and temperature."""

    def __init__(self, parent=None, limit=CPU_HISTORY_LIMIT, title="History graph",
                 mode="percent", series_count=1, series_labels=None, series_colors=None):
        super().__init__(parent)
        self.setObjectName("HistoryGraph")
        self._title = str(title)
        self.setAccessibleName(self._title)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._limit = max(2, int(limit))
        self._mode = mode
        self._series_count = max(1, int(series_count))
        self._series_labels = list(series_labels) if series_labels else []
        self._series_colors = list(series_colors) if series_colors else []
        self._points: list[tuple[float, float | tuple[float, ...]]] = []
        self._breaks: set[int] = set()
        self._pending_break = False
        self.setMinimumHeight(170)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setAccessibleDescription(f"No {self._title} history yet")

    def append(self, val1, val2=None, timestamp=None):
        if self._series_count == 1:
            moment_arg = val2 if timestamp is None else timestamp
            value = self._coerce_value(val1)
            if value is None:
                if self._points:
                    self._pending_break = True
                return
            moment = self._coerce_moment(moment_arg)
            if self._pending_break and self._points:
                self._breaks.add(len(self._points))
            self._pending_break = False
            self._points.append((moment, value))
        else:
            if isinstance(val1, (list, tuple)) and len(val1) >= 2:
                v1, v2 = val1[0], val1[1]
                moment_arg = val2 if timestamp is None else timestamp
            else:
                v1, v2 = val1, val2
                moment_arg = timestamp
            c1 = self._coerce_value(v1)
            c2 = self._coerce_value(v2)
            if c1 is None and c2 is None:
                if self._points:
                    self._pending_break = True
                return
            moment = self._coerce_moment(moment_arg)
            if self._pending_break and self._points:
                self._breaks.add(len(self._points))
            self._pending_break = False
            self._points.append((moment, (c1, c2)))

        if len(self._points) > self._limit:
            excess = len(self._points) - self._limit
            del self._points[:excess]
            kept = {b - excess for b in self._breaks if b - excess > 0}
            self._breaks = kept
        self._refresh_accessible()
        self.update()

    def segments_for_series(self, series_index: int = 0) -> list[list[tuple[float, float]]]:
        """Returns list of continuous segments of (moment, value) for the specified series."""
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for p_idx, (moment, raw_val) in enumerate(self._points):
            if p_idx in self._breaks and current:
                segments.append(current)
                current = []
            val = raw_val[series_index] if self._series_count > 1 else raw_val
            if val is None:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append((moment, float(val)))
        if current:
            segments.append(current)
        return segments

    def _coerce_value(self, val):
        if self._mode == "percent":
            return _coerce_percent(val)
        elif self._mode == "rate":
            return _coerce_rate(val)
        else:
            return _coerce_float(val)

    def _coerce_moment(self, timestamp):
        if timestamp is None:
            return time.monotonic()
        try:
            m = float(timestamp)
            return m if math.isfinite(m) else time.monotonic()
        except (TypeError, ValueError):
            return time.monotonic()

    def gap(self):
        """Break the trace; next known reading starts a new segment."""
        if self._points:
            self._pending_break = True
        self.update()

    def clear(self):
        self._points = []
        self._breaks = set()
        self._pending_break = False
        self.setAccessibleDescription(f"No {self._title} history yet")
        self.update()

    @property
    def samples(self):
        if self._series_count == 1:
            return [v for _, v in self._points]
        return [vals for _, vals in self._points]

    @property
    def timestamps(self):
        return [t for t, _ in self._points]

    def _refresh_accessible(self):
        count = len(self._points)
        if not count:
            self.setAccessibleDescription(f"No {self._title} history yet")
            return
        latest = self._points[-1][1]
        if self._series_count == 1:
            if latest is None:
                latest_str = UNAVAILABLE
            elif self._mode == "watts":
                latest_str = f"{latest:.1f} W"
            elif self._mode == "rpm":
                latest_str = f"{int(round(latest))} RPM"
            elif self._mode == "temp":
                latest_str = f"{latest:.1f} °C"
            elif self._mode == "rate":
                latest_str = _format_rate_unit(latest)
            else:
                latest_str = f"{latest:.0f}"
        else:
            parts = []
            for v in latest:
                if v is None:
                    parts.append(UNAVAILABLE)
                elif self._mode == "rate":
                    parts.append(_format_rate_unit(v))
                elif self._mode == "temp":
                    parts.append(f"{v:.1f} °C")
                elif self._mode == "watts":
                    parts.append(f"{v:.1f} W")
                elif self._mode == "rpm":
                    parts.append(f"{int(round(v))} RPM")
                elif self._mode == "percent":
                    parts.append(f"{v:.0f}%")
                else:
                    parts.append(f"{v:.0f}")
            latest_str = ", ".join(parts)
        self.setAccessibleDescription(
            f"{self._title}: latest {latest_str}, {count} readings, {self.time_labels()[0]}"
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
        if len(self._points) < 2:
            return "1 reading", "", "", "latest"
        span = max(0.0, self._points[-1][0] - self._points[0][0])
        return (f"span {self._duration_label(span)}",
                f"−{self._duration_label(span)}" if span else "",
                f"−{self._duration_label(span / 2)}" if span else "",
                "latest")

    def _time_fraction(self, moment):
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

            if self._mode == "percent":
                y_max = 100.0
                labels = ("100%", "50%", "0%")
            elif self._mode == "rate":
                max_val = 0.0
                for _, val in self._points:
                    if isinstance(val, (int, float)):
                        max_val = max(max_val, float(val))
                    elif isinstance(val, (tuple, list)):
                        for v in val:
                            if v is not None:
                                max_val = max(max_val, float(v))
                y_max = max(1024.0, max_val * 1.1)
                labels = (_format_rate_unit(y_max), _format_rate_unit(y_max / 2.0), "0 B/s")
            elif self._mode == "temp":
                max_val = 0.0
                for _, val in self._points:
                    if isinstance(val, (int, float)):
                        max_val = max(max_val, float(val))
                    elif isinstance(val, (tuple, list)):
                        for v in val:
                            if v is not None:
                                max_val = max(max_val, float(v))
                y_max = max(100.0, max_val * 1.1)
                labels = (f"{int(round(y_max))} °C", f"{int(round(y_max / 2.0))} °C", "0 °C")
            elif self._mode == "watts":
                max_val = 0.0
                for _, val in self._points:
                    if isinstance(val, (int, float)):
                        max_val = max(max_val, float(val))
                    elif isinstance(val, (tuple, list)):
                        for v in val:
                            if v is not None:
                                max_val = max(max_val, float(v))
                y_max = max(10.0, max_val * 1.15)
                if y_max >= 100.0:
                    labels = (f"{int(round(y_max))} W", f"{int(round(y_max / 2.0))} W", "0 W")
                else:
                    labels = (f"{y_max:.1f} W", f"{y_max / 2.0:.1f} W", "0 W")
            elif self._mode == "rpm":
                max_val = 0.0
                for _, val in self._points:
                    if isinstance(val, (int, float)):
                        max_val = max(max_val, float(val))
                    elif isinstance(val, (tuple, list)):
                        for v in val:
                            if v is not None:
                                max_val = max(max_val, float(v))
                y_max = max(3000.0, max_val * 1.15)
                labels = (f"{int(round(y_max))} RPM", f"{int(round(y_max / 2.0))} RPM", "0 RPM")
            else:
                y_max = 100.0
                labels = ("100", "50", "0")

            left = max(metrics.horizontalAdvance(lbl) for lbl in labels) + 14
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

            grid_color = QtGui.QColor(mid)
            grid_color.setAlpha(120)
            grid_pen = QtGui.QPen(grid_color, 1)
            grid_pen.setCosmetic(True)
            painter.setPen(grid_pen)
            for frac in (1.0, 0.5, 0.0):
                y = plot.bottom() - int(round(plot.height() * frac))
                painter.drawLine(plot.left(), y, plot.right(), y)

            painter.setPen(text)
            painter.drawText(4, plot.top() + metrics.ascent(), labels[0])
            painter.drawText(4, plot.center().y() + metrics.ascent() // 2, labels[1])
            painter.drawText(4, plot.bottom(), labels[2])

            if not self._points:
                painter.drawText(plot, QtCore.Qt.AlignmentFlag.AlignCenter, "No samples yet")
                return

            colors = []
            if self._series_colors:
                colors = list(self._series_colors)
            if len(colors) < 1:
                colors.append(highlight)
            if len(colors) < 2:
                colors.append(_secondary_graph_color(highlight, base))

            def to_point(moment, val):
                x = plot.left() + self._time_fraction(moment) * (plot.width() - 1)
                clamped_val = max(0.0, min(y_max, val))
                y = plot.bottom() - (clamped_val / y_max) * (plot.height() - 1)
                return QtCore.QPointF(x, y)

            for s_idx in range(self._series_count):
                series_color = colors[s_idx % len(colors)]
                raw_segs = self.segments_for_series(s_idx)
                segments: list[list[QtCore.QPointF]] = [
                    [to_point(m, v) for m, v in seg]
                    for seg in raw_segs if seg
                ]

                if s_idx == 0:
                    top_fill = QtGui.QColor(series_color)
                    top_fill.setAlpha(72)
                    bottom_fill = QtGui.QColor(series_color)
                    bottom_fill.setAlpha(10)
                    gradient = QtGui.QLinearGradient(0, plot.top(), 0, plot.bottom())
                    gradient.setColorAt(0.0, top_fill)
                    gradient.setColorAt(1.0, bottom_fill)
                    for seg in segments:
                        if len(seg) >= 2:
                            poly = QtGui.QPolygonF(seg)
                            poly.append(QtCore.QPointF(seg[-1].x(), plot.bottom()))
                            poly.append(QtCore.QPointF(seg[0].x(), plot.bottom()))
                            painter.setPen(QtCore.Qt.PenStyle.NoPen)
                            painter.setBrush(gradient)
                            painter.drawPolygon(poly)
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

                trace_pen = QtGui.QPen(series_color, 2.0)
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
                    for pt in seg[1:]:
                        path.lineTo(pt)
                    painter.drawPath(path)

                latest_point = segments[-1][-1] if segments else None
                if latest_point is not None:
                    painter.setPen(QtGui.QPen(base, 1.5))
                    painter.setBrush(series_color)
                    painter.drawEllipse(latest_point, 3.5, 3.5)
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

            painter.setPen(text)
            span_label, left_label, middle_label, right_label = self.time_labels()
            painter.drawText(plot.left() + 4, plot.top() + metrics.ascent(), span_label)
            axis = QtCore.QRect(plot.left(), plot.bottom() + 4, plot.width(), metrics.height())
            painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignLeft, left_label)
            painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignRight, right_label)
            occupied = metrics.horizontalAdvance(left_label + right_label + middle_label) + 30
            if plot.width() >= occupied:
                painter.drawText(axis, QtCore.Qt.AlignmentFlag.AlignHCenter, middle_label)

            if self._series_labels and self._points:
                latest_raw = self._points[-1][1]
                legend_items = []
                for s_idx, label in enumerate(self._series_labels):
                    val = latest_raw[s_idx] if self._series_count > 1 else latest_raw
                    if val is None:
                        val_str = UNAVAILABLE
                    elif self._mode == "rate":
                        val_str = _format_rate_unit(val)
                    elif self._mode == "temp":
                        val_str = f"{val:.1f} °C"
                    elif self._mode == "watts":
                        val_str = f"{val:.1f} W"
                    elif self._mode == "rpm":
                        val_str = f"{int(round(val))} RPM"
                    else:
                        val_str = f"{val:.0f}%"
                    legend_items.append((label, val_str, colors[s_idx % len(colors)]))

                legend_x = plot.right() - 6
                legend_y = plot.top() + metrics.ascent()
                for label, val_str, col in reversed(legend_items):
                    text_str = f"{label}: {val_str}"
                    text_w = metrics.horizontalAdvance(text_str)
                    dot_x = legend_x - text_w - 14
                    if dot_x < plot.left() + metrics.horizontalAdvance(span_label) + 30:
                        break
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(col)
                    painter.drawEllipse(QtCore.QPointF(dot_x + 4, legend_y - metrics.ascent() // 3), 3.0, 3.0)
                    painter.setPen(text)
                    painter.drawText(dot_x + 12, legend_y, text_str)
                    legend_x = dot_x - 14

        finally:
            painter.end()


class CpuGraph(HistoryGraph):
    """History graph with real timestamps; gaps break the trace."""

    def __init__(self, parent=None, limit=CPU_HISTORY_LIMIT):
        super().__init__(
            parent=parent,
            limit=limit,
            title="CPU usage history graph",
            mode="percent",
            series_count=1,
            series_labels=None,
        )
        self.setObjectName("CpuGraph")
        self.setAccessibleName("CPU usage history graph")
        self.setAccessibleDescription("No CPU history yet")

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


class CoreBarWidget(QtWidgets.QFrame):
    """Visual meter for a single CPU core with name, frequency and usage bar."""

    def __init__(self, core_index: int, parent=None):
        super().__init__(parent)
        self.setObjectName("coreMeter")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._title = QtWidgets.QLabel(f"Core {core_index}", self)
        self._title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        font = QtGui.QFont(self._title.font())
        font.setBold(True)
        self._title.setFont(font)

        self._freq = QtWidgets.QLabel("", self)
        self._freq.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._freq.setObjectName("secondaryText")

        header.addWidget(self._title, 0)
        header.addStretch(1)
        header.addWidget(self._freq, 0)
        layout.addLayout(header)

        self.bar = UsageBar(self)
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

    def update_core(self, percent, freq_mhz=None):
        self.bar.set_usage(percent)
        if freq_mhz is not None:
            try:
                self._freq.setText(f"{float(freq_mhz):.0f} MHz")
            except (ValueError, TypeError):
                self._freq.setText("")
        else:
            self._freq.setText("")
        pct_text = f"{percent:.0f}%" if percent is not None else UNAVAILABLE
        self.setAccessibleName(f"{self._title.text()}: {pct_text}")
        self.setAccessibleDescription(
            f"{self._title.text()} utilization {pct_text}, frequency {self._freq.text()}"
        )


class PerCoreGrid(QtWidgets.QWidget):
    """Responsive grid container for CoreBarWidgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("perCoreGrid")
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._widgets: list[CoreBarWidget] = []
        self._columns = 4

    def update_cores(self, per_core_percents, frequencies_mhz=None):
        per_core = per_core_percents or []
        freqs = frequencies_mhz or []
        count = len(per_core)
        if len(self._widgets) != count:
            for w in self._widgets:
                self._layout.removeWidget(w)
                w.deleteLater()
            self._widgets.clear()
            for i in range(count):
                w = CoreBarWidget(i, self)
                self._widgets.append(w)
            self._reflow()

        for i, w in enumerate(self._widgets):
            pct = per_core[i] if i < len(per_core) else None
            freq = freqs[i] if i < len(freqs) else None
            w.update_core(pct, freq)

    def set_columns(self, columns: int):
        cols = max(1, int(columns))
        if self._columns != cols:
            self._columns = cols
            self._reflow()

    def _reflow(self):
        for i, w in enumerate(self._widgets):
            self._layout.addWidget(w, i // self._columns, i % self._columns)


class BatteryPackCard(QtWidgets.QFrame):
    """Card representing an individual battery pack with charge, health and power stats."""

    def __init__(self, name="Battery", parent=None):
        super().__init__(parent)
        self.setObjectName("detailPanel")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._name_label = QtWidgets.QLabel(str(name), self)
        font = QtGui.QFont(self._name_label.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 2)
        self._name_label.setFont(font)
        self._name_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)

        self._status_badge = QtWidgets.QLabel("Unknown", self)
        self._status_badge.setObjectName("statusBadge")
        self._status_badge.setTextFormat(QtCore.Qt.TextFormat.PlainText)

        header.addWidget(self._name_label, 0)
        header.addStretch(1)
        header.addWidget(self._status_badge, 0)
        layout.addLayout(header)

        bars_layout = QtWidgets.QVBoxLayout()
        bars_layout.setSpacing(6)

        charge_row = QtWidgets.QHBoxLayout()
        charge_lbl = QtWidgets.QLabel("Charge", self)
        charge_lbl.setObjectName("secondaryText")
        self._charge_detail = QtWidgets.QLabel("", self)
        self._charge_detail.setObjectName("secondaryText")
        charge_row.addWidget(charge_lbl)
        charge_row.addStretch(1)
        charge_row.addWidget(self._charge_detail)
        bars_layout.addLayout(charge_row)

        self.charge_bar = UsageBar(self)
        self.charge_bar.setFixedHeight(10)
        self.charge_bar.setTextVisible(False)
        bars_layout.addWidget(self.charge_bar)

        health_row = QtWidgets.QHBoxLayout()
        health_lbl = QtWidgets.QLabel("Health", self)
        health_lbl.setObjectName("secondaryText")
        self._health_detail = QtWidgets.QLabel("", self)
        self._health_detail.setObjectName("secondaryText")
        health_row.addWidget(health_lbl)
        health_row.addStretch(1)
        health_row.addWidget(self._health_detail)
        bars_layout.addLayout(health_row)

        self.health_bar = UsageBar(self)
        self.health_bar.setFixedHeight(10)
        self.health_bar.setTextVisible(False)
        bars_layout.addWidget(self.health_bar)
        layout.addLayout(bars_layout)

        self._stats_label = QtWidgets.QLabel("", self)
        self._stats_label.setObjectName("secondaryText")
        self._stats_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label)

    def update_pack(self, pack: dict):
        name = pack.get("name") or "Battery"
        self._name_label.setText(str(name))
        status = pack.get("status") or "Unknown"
        thresh = pack.get("charge_stop_threshold")
        if thresh:
            status += f" (limit {thresh}%)"
        self._status_badge.setText(status)

        pct = pack.get("percent")
        self.charge_bar.set_usage(pct)
        wh = pack.get("energy_wh")
        full_wh = pack.get("full_energy_wh")
        wh_text = f"{wh:.1f} / {full_wh:.1f} Wh" if (wh is not None and full_wh is not None) else ""
        pct_text = f"{pct:.0f}%" if pct is not None else UNAVAILABLE
        self._charge_detail.setText(f"{pct_text} · {wh_text}" if wh_text else pct_text)

        hpct = pack.get("health_percent")
        self.health_bar.set_usage(hpct)
        cycles = pack.get("cycles")
        cycles_text = f"{int(cycles):,} cycles" if cycles is not None else ""
        hpct_text = f"{hpct:.0f}%" if hpct is not None else UNAVAILABLE
        self._health_detail.setText(f"{hpct_text} · {cycles_text}" if cycles_text else hpct_text)

        parts = []
        volts = pack.get("voltage_volts")
        if volts is not None:
            parts.append(f"{volts:.2f} V")
        watts = pack.get("power_watts")
        if watts is not None:
            parts.append(f"{watts:.1f} W")
        time_rem = pack.get("time_remaining_seconds")
        if time_rem is not None:
            try:
                t = int(float(time_rem))
                h, r = divmod(t, 3600)
                m, _ = divmod(r, 60)
                parts.append(f"Est. {h}h {m:02d}m remaining")
            except Exception:
                pass
        self._stats_label.setText(" · ".join(parts) if parts else "")
        self.setAccessibleName(f"Battery {name}: {pct_text}, {status}")



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


class PowerSupplyCard(QtWidgets.QFrame):
    """Card representing an AC adapter or USB Type-C PD power supply."""

    def __init__(self, name="Power Supply", parent=None):
        super().__init__(parent)
        self.setObjectName("detailPanel")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._name_label = QtWidgets.QLabel(str(name), self)
        font = QtGui.QFont(self._name_label.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1)
        self._name_label.setFont(font)
        self._name_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)

        self._status_badge = QtWidgets.QLabel("Unknown", self)
        self._status_badge.setObjectName("statusBadge")
        self._status_badge.setTextFormat(QtCore.Qt.TextFormat.PlainText)

        header.addWidget(self._name_label, 0)
        header.addStretch(1)
        header.addWidget(self._status_badge, 0)
        layout.addLayout(header)

        self._type_label = QtWidgets.QLabel("", self)
        self._type_label.setObjectName("secondaryText")
        self._type_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self._type_label)

        self._specs_label = QtWidgets.QLabel("", self)
        self._specs_label.setObjectName("secondaryText")
        self._specs_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self._specs_label)

    def update_supply(self, ps: dict):
        name = ps.get("name") or "Power supply"
        self._name_label.setText(str(name))
        online = ps.get("online")
        if online is True:
            badge_text = "Connected"
        elif online is False:
            badge_text = "Disconnected"
        else:
            badge_text = ps.get("status") or "Unknown"
        self._status_badge.setText(badge_text)

        typ = ps.get("type") or "Power supply"
        usb_typ = ps.get("usb_type")
        type_str = f"Type: {typ}" + (f" ({usb_typ})" if usb_typ else "")
        self._type_label.setText(type_str)

        specs = []
        volts = ps.get("voltage_volts")
        amps = ps.get("current_amperes")
        if volts is not None:
            specs.append(f"{volts:.2f} V")
        if amps is not None:
            specs.append(f"{amps:.2f} A")
        if volts is not None and amps is not None:
            watts = volts * amps
            specs.append(f"{watts:.1f} W")
        self._specs_label.setText(" · ".join(specs) if specs else "No electrical telemetry reported")
        self.setAccessibleName(f"{name}: {badge_text}")
        self.setAccessibleDescription(f"{name} ({type_str}), status {badge_text}, {self._specs_label.text()}")


class ThermalZoneBar(QtWidgets.QFrame):
    """Visual meter for a thermal sensor with label, temperature, and colored bar."""

    def __init__(self, label="Thermal Sensor", parent=None):
        super().__init__(parent)
        self.setObjectName("coreMeter")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._title = QtWidgets.QLabel(str(label), self)
        self._title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        font = QtGui.QFont(self._title.font())
        font.setBold(True)
        self._title.setFont(font)

        self._temp_label = QtWidgets.QLabel("", self)
        self._temp_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._temp_label.setObjectName("secondaryText")

        header.addWidget(self._title, 0)
        header.addStretch(1)
        header.addWidget(self._temp_label, 0)
        layout.addLayout(header)

        self.bar = UsageBar(self)
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

    def update_sensor(self, label, celsius, crit_celsius=None):
        self._title.setText(str(label))
        if celsius is not None:
            try:
                c_val = float(celsius)
                if not math.isfinite(c_val):
                    raise ValueError("nonfinite temperature")
            except (ValueError, TypeError):
                self.bar.set_usage(None)
                self.bar.hide()
                self._temp_label.setText(UNAVAILABLE)
                self.setAccessibleName(f"{self._title.text()}: {self._temp_label.text()}")
                self.setAccessibleDescription(f"{self._title.text()} temperature {self._temp_label.text()}")
                return

            crit_val = None
            if crit_celsius is not None:
                try:
                    cv = float(crit_celsius)
                    if math.isfinite(cv) and cv > 0:
                        crit_val = cv
                except (ValueError, TypeError):
                    crit_val = None

            if crit_val is not None:
                pct = max(0.0, min(100.0, (c_val / crit_val) * 100.0))
                self.bar.set_usage(pct)
                self.bar.show()
                self._temp_label.setText(f"{c_val:.1f} °C (crit {crit_val:.0f}°C)")
            else:
                self.bar.set_usage(None)
                self.bar.hide()
                self._temp_label.setText(f"{c_val:.1f} °C")
        else:
            self.bar.set_usage(None)
            self.bar.hide()
            self._temp_label.setText(UNAVAILABLE)
        self.setAccessibleName(f"{self._title.text()}: {self._temp_label.text()}")
        self.setAccessibleDescription(f"{self._title.text()} temperature {self._temp_label.text()}")


class ThermalZoneGrid(QtWidgets.QWidget):
    """Responsive grid container for ThermalZoneBar widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("thermalZoneGrid")
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._widgets: list[ThermalZoneBar] = []
        self._columns = 3
        self._no_sensors_label = QtWidgets.QLabel("No temperature sensors detected", self)
        self._no_sensors_label.setObjectName("secondaryText")
        self._no_sensors_label.setWordWrap(True)
        self._layout.addWidget(self._no_sensors_label, 0, 0)
        self._cap_label = QtWidgets.QLabel("", self)
        self._cap_label.setObjectName("secondaryText")
        self._cap_label.setWordWrap(True)
        self._cap_label.setVisible(False)
        self._layout.addWidget(self._cap_label, 1, 0)

    def update_sensors(self, sensors: list[dict]):
        valid_sensors = [s for s in (sensors or []) if isinstance(s, dict) and s.get("celsius") is not None]
        if not valid_sensors:
            self._no_sensors_label.setVisible(True)
            self._cap_label.setVisible(False)
            for w in self._widgets:
                w.setVisible(False)
            return

        self._no_sensors_label.setVisible(False)
        count = min(12, len(valid_sensors))
        if len(valid_sensors) > 12:
            self._cap_label.setText(f"Showing 12 of {len(valid_sensors)} sensors (all available in table below)")
            self._cap_label.setVisible(True)
        else:
            self._cap_label.setVisible(False)

        if len(self._widgets) != count:
            for w in self._widgets:
                self._layout.removeWidget(w)
                w.deleteLater()
            self._widgets.clear()
            for _ in range(count):
                w = ThermalZoneBar("", self)
                self._widgets.append(w)
            self._reflow()

        for i in range(count):
            s = valid_sensors[i]
            label = s.get("label") or s.get("name") or f"Sensor {i+1}"
            self._widgets[i].setVisible(True)
            self._widgets[i].update_sensor(label, s.get("celsius"), s.get("critical_celsius"))

    def set_columns(self, columns: int):
        cols = max(1, int(columns))
        if self._columns != cols:
            self._columns = cols
            self._reflow()

    def _reflow(self):
        for i, w in enumerate(self._widgets):
            self._layout.addWidget(w, i // self._columns, i % self._columns)
        if self._cap_label is not None:
            row = (len(self._widgets) + self._columns - 1) // self._columns if self._widgets else 1
            self._layout.addWidget(self._cap_label, row, 0, 1, self._columns)


class FanMeterWidget(QtWidgets.QFrame):
    """Visual meter for a cooling fan with RPM and status."""

    def __init__(self, label="Cooling Fan", parent=None):
        super().__init__(parent)
        self.setObjectName("coreMeter")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._title = QtWidgets.QLabel(str(label), self)
        self._title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        font = QtGui.QFont(self._title.font())
        font.setBold(True)
        self._title.setFont(font)

        self._rpm_label = QtWidgets.QLabel("", self)
        self._rpm_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._rpm_label.setObjectName("secondaryText")

        header.addWidget(self._title, 0)
        header.addStretch(1)
        header.addWidget(self._rpm_label, 0)
        layout.addLayout(header)

        self.bar = UsageBar(self)
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

    def update_fan(self, label, rpm, max_rpm=None):
        self._title.setText(str(label))
        if rpm is not None:
            try:
                r_val = float(rpm)
                if not math.isfinite(r_val) or r_val < 0:
                    raise ValueError("invalid fan speed")
                status = "Off / 0 RPM" if r_val <= 0 else f"{int(round(r_val))} RPM"
                self._rpm_label.setText(status)
                if max_rpm is not None:
                    try:
                        m_val = float(max_rpm)
                        if math.isfinite(m_val) and m_val > 0:
                            pct = max(0.0, min(100.0, (r_val / m_val) * 100.0))
                            self.bar.set_usage(pct)
                            self.bar.show()
                        else:
                            self.bar.set_usage(None)
                            self.bar.hide()
                    except (ValueError, TypeError):
                        self.bar.set_usage(None)
                        self.bar.hide()
                else:
                    self.bar.set_usage(None)
                    self.bar.hide()
            except (ValueError, TypeError):
                self.bar.set_usage(None)
                self.bar.hide()
                self._rpm_label.setText(UNAVAILABLE)
        else:
            self.bar.set_usage(None)
            self.bar.hide()
            self._rpm_label.setText(UNAVAILABLE)
        self.setAccessibleName(f"{self._title.text()}: {self._rpm_label.text()}")
        self.setAccessibleDescription(f"{self._title.text()} speed {self._rpm_label.text()}")


class FanSpeedGrid(QtWidgets.QWidget):
    """Responsive grid container for FanMeterWidget components."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fanSpeedGrid")
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._widgets: list[FanMeterWidget] = []
        self._columns = 2
        self._no_fans_label = QtWidgets.QLabel("No fan readings are available.", self)
        self._no_fans_label.setObjectName("secondaryText")
        self._no_fans_label.setWordWrap(True)
        self._layout.addWidget(self._no_fans_label, 0, 0)

    def update_fans(self, fans: list[dict]):
        valid_fans = [f for f in (fans or []) if isinstance(f, dict)]
        if not valid_fans:
            self._no_fans_label.setVisible(True)
            for w in self._widgets:
                w.setVisible(False)
            return

        self._no_fans_label.setVisible(False)
        count = len(valid_fans)
        if len(self._widgets) != count:
            for w in self._widgets:
                self._layout.removeWidget(w)
                w.deleteLater()
            self._widgets.clear()
            for _ in range(count):
                w = FanMeterWidget("", self)
                self._widgets.append(w)
            self._reflow()

        for i, f in enumerate(valid_fans):
            label = f.get("label") or f.get("name") or f"Fan {i+1}"
            self._widgets[i].setVisible(True)
            self._widgets[i].update_fan(label, f.get("rpm"), f.get("max_rpm"))

    def set_columns(self, columns: int):
        cols = max(1, int(columns))
        if self._columns != cols:
            self._columns = cols
            self._reflow()

    def _reflow(self):
        for i, w in enumerate(self._widgets):
            self._layout.addWidget(w, i // self._columns, i % self._columns)


class CollapsibleSection(QtWidgets.QWidget):
    """A disclosure section with a native checkable button and arrow icon."""

    toggled = QtCore.Signal(bool)

    def __init__(self, title: str, content_widget: QtWidgets.QWidget, expanded: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self._title = str(title)
        self._content_widget = content_widget

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # A native checkable button keeps keyboard and accessibility behavior.
        self._toggle_button = QtWidgets.QPushButton(self)
        self._toggle_button.setObjectName("collapsibleToggle")
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(bool(expanded))
        self._toggle_button.setAutoDefault(False)
        self._toggle_button.setIconSize(QtCore.QSize(16, 16))
        self._toggle_button.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._toggle_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        font = QtGui.QFont(self._toggle_button.font())
        font.setBold(True)
        self._toggle_button.setFont(font)
        self._toggle_button.toggled.connect(self._on_toggled)

        lay.addWidget(self._toggle_button)

        if content_widget is not None:
            content_widget.setParent(self)
            lay.addWidget(content_widget)
            content_widget.setVisible(bool(expanded))

        self._update_toggle_state(bool(expanded))

    @property
    def content_widget(self) -> QtWidgets.QWidget:
        return self._content_widget

    def isExpanded(self) -> bool:  # noqa: N802
        return self._toggle_button.isChecked()

    def is_expanded(self) -> bool:
        return self._toggle_button.isChecked()

    def setExpanded(self, expanded: bool):  # noqa: N802
        self._toggle_button.setChecked(bool(expanded))

    def set_expanded(self, expanded: bool):
        self._toggle_button.setChecked(bool(expanded))

    def toggle(self):
        self._toggle_button.toggle()

    def _on_toggled(self, checked: bool):
        self._update_toggle_state(checked)
        if self._content_widget is not None:
            self._content_widget.setVisible(checked)
        self.updateGeometry()
        if self.parentWidget():
            self.parentWidget().updateGeometry()
        self.toggled.emit(checked)

    def _update_toggle_state(self, checked: bool):
        arrow = QtWidgets.QStyle.StandardPixmap.SP_ArrowDown if checked else QtWidgets.QStyle.StandardPixmap.SP_ArrowRight
        self._toggle_button.setText(self._title)
        self._toggle_button.setIcon(self.style().standardIcon(arrow, None, self._toggle_button))
        state_text = "expanded" if checked else "collapsed"
        self._toggle_button.setAccessibleName(f"{self._title} section")
        self._toggle_button.setAccessibleDescription(
            f"{self._title} section is {state_text}. Press to {'collapse' if checked else 'expand'}."
        )

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if hasattr(self, "_toggle_button") and event.type() in (
            QtCore.QEvent.Type.PaletteChange,
            QtCore.QEvent.Type.ApplicationPaletteChange,
            QtCore.QEvent.Type.StyleChange,
        ):
            self._update_toggle_state(self.isExpanded())
