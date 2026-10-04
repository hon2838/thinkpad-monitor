"""Compact native vector icons for the Laptop Monitor UI.

Stroke-only 24x24 glyphs painted with QPainter (round caps/joins) using the
native QPalette (Text / HighlightedText) so icons follow light/dark themes and
remain crisp at any DPI via QIconEngine.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

__all__ = [
    "ICON_NAMES",
    "available_icons",
    "has_icon",
    "icon",
]

GRID = 24.0
_STROKE = 1.8

ICON_NAMES = (
    "overview",
    "cpu",
    "memory",
    "storage",
    "battery",
    "network",
    "thermals",
    "gpu",
    "power",
    "system",
    "fan",
    "pause",
    "resume",
    "refresh",
    "copy",
    "laptop",
)

_ALIASES = {
    "disk": "storage",
    "hdd": "storage",
    "wifi": "network",
    "temp": "thermals",
    "thermal": "thermals",
    "play": "resume",
    "reload": "refresh",
}


def _normalize(name) -> str:
    if not isinstance(name, str):
        raise TypeError("icon name must be str")
    key = name.strip().lower().replace("-", "_")
    return _ALIASES.get(key, key)


def available_icons() -> list[str]:
    return list(ICON_NAMES)


def has_icon(name) -> bool:
    try:
        return _normalize(name) in _PAINTERS
    except (TypeError, AttributeError):
        return False


def _resolve_palette(palette) -> QtGui.QPalette:
    if palette is None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            return QtGui.QPalette(app.palette())
        return QtGui.QPalette()
    if isinstance(palette, QtGui.QPalette):
        return QtGui.QPalette(palette)
    raise TypeError("palette must be a QPalette or None")


def _mode_color(palette: QtGui.QPalette, mode) -> QtGui.QColor:
    if mode == QtGui.QIcon.Mode.Selected:
        return palette.color(QtGui.QPalette.ColorRole.HighlightedText)
    if mode == QtGui.QIcon.Mode.Disabled:
        return palette.color(
            QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text
        )
    return palette.color(QtGui.QPalette.ColorRole.Text)


def _dot(painter: QtGui.QPainter, x: float, y: float, r: float) -> None:
    painter.save()
    painter.setBrush(painter.pen().color())
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(QtCore.QPointF(x, y), r, r)
    painter.restore()


def _base_pen(color: QtGui.QColor, width: float = _STROKE) -> QtGui.QPen:
    pen = QtGui.QPen(
        color,
        width,
        QtCore.Qt.PenStyle.SolidLine,
        QtCore.Qt.PenCapStyle.RoundCap,
        QtCore.Qt.PenJoinStyle.RoundJoin,
    )
    pen.setCosmetic(False)
    return pen


def _draw_overview(p, _c):
    for x, y in ((4.0, 4.0), (13.0, 4.0), (4.0, 13.0), (13.0, 13.0)):
        p.drawRoundedRect(QtCore.QRectF(x, y, 7.0, 7.0), 1.6, 1.6)


def _draw_cpu(p, _c):
    p.drawRoundedRect(QtCore.QRectF(7, 7, 10, 10), 1.2, 1.2)
    p.drawRoundedRect(QtCore.QRectF(10.4, 10.4, 3.2, 3.2), 0.6, 0.6)
    for x in (9.6, 12.0, 14.4):
        p.drawLine(QtCore.QLineF(x, 3.6, x, 7.0))
        p.drawLine(QtCore.QLineF(x, 17.0, x, 20.4))
    for y in (9.6, 12.0, 14.4):
        p.drawLine(QtCore.QLineF(3.6, y, 7.0, y))
        p.drawLine(QtCore.QLineF(17.0, y, 20.4, y))


def _draw_memory(p, _c):
    p.drawRoundedRect(QtCore.QRectF(3, 8, 18, 7.5), 1.2, 1.2)
    p.drawLine(QtCore.QLineF(3.0, 11.8, 21.0, 11.8))
    for x in (6.0, 9.0, 12.0, 15.0, 18.0):
        p.drawLine(QtCore.QLineF(x, 15.5, x, 18.4))
    p.drawLine(QtCore.QLineF(6.4, 8.0, 6.4, 11.8))


def _draw_storage(p, _c):
    p.drawRoundedRect(QtCore.QRectF(3, 7, 18, 10), 2.0, 2.0)
    p.drawLine(QtCore.QLineF(3.0, 11.0, 21.0, 11.0))
    _dot(p, 6.2, 14.0, 1.05)
    p.drawLine(QtCore.QLineF(10.5, 14.0, 17.5, 14.0))


def _draw_battery(p, c):
    p.drawRoundedRect(QtCore.QRectF(2.8, 8, 16.2, 8.4), 1.8, 1.8)
    p.drawRoundedRect(QtCore.QRectF(19.6, 10.6, 2.2, 3.2), 0.9, 0.9)
    p.setBrush(c)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawRoundedRect(QtCore.QRectF(5.2, 10.2, 7.6, 4.0), 0.9, 0.9)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.setPen(_base_pen(c))


def _draw_network(p, _c):
    _dot(p, 12.0, 18.2, 1.25)
    for r in (4.2, 7.4, 10.6):
        rect = QtCore.QRectF(12 - r, 18.2 - r, 2 * r, 2 * r)
        p.drawArc(rect, int(35 * 16), int(110 * 16))


def _draw_thermals(p, _c):
    p.drawRoundedRect(QtCore.QRectF(10, 3.6, 4.2, 11.2), 2.1, 2.1)
    p.drawEllipse(QtCore.QRectF(12 - 3.4, 18.4 - 3.4, 6.8, 6.8))
    p.drawLine(QtCore.QLineF(12.1, 8.6, 12.1, 17.6))
    _dot(p, 12.1, 18.4, 1.3)


def _draw_gpu(p, _c):
    p.drawRoundedRect(QtCore.QRectF(2.8, 8, 14.4, 9.5), 1.2, 1.2)
    p.drawLine(QtCore.QLineF(19.4, 4.6, 19.4, 19.4))
    p.drawLine(QtCore.QLineF(17.2, 6.2, 19.4, 6.2))
    p.drawLine(QtCore.QLineF(17.2, 17.8, 19.4, 17.8))
    p.drawEllipse(QtCore.QRectF(9.2 - 3.0, 12.7 - 3.0, 6.0, 6.0))
    _dot(p, 9.2, 12.7, 0.9)
    p.drawLine(QtCore.QLineF(6.0, 17.5, 6.0, 20.2))
    p.drawLine(QtCore.QLineF(11.0, 17.5, 11.0, 20.2))


def _draw_power(p, _c):
    p.drawArc(QtCore.QRectF(6, 7, 12, 12), int(120 * 16), int(300 * 16))
    p.drawLine(QtCore.QLineF(12.0, 3.8, 12.0, 11.0))


def _draw_system(p, _c):
    p.drawEllipse(QtCore.QRectF(12 - 3.4, 12 - 3.4, 6.8, 6.8))
    for deg in range(0, 360, 45):
        import math

        a = math.radians(deg)
        x1, y1 = 12 + 5.1 * math.cos(a), 12 + 5.1 * math.sin(a)
        x2, y2 = 12 + 7.4 * math.cos(a), 12 + 7.4 * math.sin(a)
        p.drawLine(QtCore.QLineF(x1, y1, x2, y2))


def _draw_fan(p, _c):
    import math

    p.drawEllipse(QtCore.QRectF(12 - 8.0, 12 - 8.0, 16.0, 16.0))
    for base in (0, 120, 240):
        a0 = math.radians(base)
        a1 = math.radians(base + 70)
        path = QtGui.QPainterPath(QtCore.QPointF(12, 12))
        c1 = QtCore.QPointF(12 + 2.6 * math.cos(a0), 12 + 2.6 * math.sin(a0))
        c2 = QtCore.QPointF(12 + 5.6 * math.cos(a1), 12 + 5.6 * math.sin(a1))
        end = QtCore.QPointF(12 + 6.6 * math.cos(a1), 12 + 6.6 * math.sin(a1))
        path.cubicTo(c1, c2, end)
        p.drawPath(path)
    _dot(p, 12.0, 12.0, 1.0)


def _draw_pause(p, c):
    p.save()
    p.setPen(_base_pen(c, 3.2))
    p.drawLine(QtCore.QLineF(9.2, 6.0, 9.2, 18.0))
    p.drawLine(QtCore.QLineF(14.8, 6.0, 14.8, 18.0))
    p.restore()


def _draw_resume(p, _c):
    path = QtGui.QPainterPath()
    path.moveTo(9.0, 5.8)
    path.lineTo(18.4, 12.0)
    path.lineTo(9.0, 18.2)
    path.closeSubpath()
    p.drawPath(path)


def _draw_refresh(p, _c):
    p.drawArc(QtCore.QRectF(5, 6, 14, 14), int(40 * 16), int(275 * 16))
    # Arrowhead at the arc end (top-right).
    head = QtGui.QPainterPath()
    head.moveTo(19.6, 6.2)
    head.lineTo(16.4, 6.6)
    head.moveTo(19.6, 6.2)
    head.lineTo(18.4, 9.6)
    p.drawPath(head)


def _draw_copy(p, _c):
    p.drawRoundedRect(QtCore.QRectF(8.8, 4.2, 10.4, 10.4), 1.6, 1.6)
    p.drawRoundedRect(QtCore.QRectF(4.4, 9.2, 10.4, 10.4), 1.6, 1.6)


def _draw_laptop(p, _c):
    p.drawRoundedRect(QtCore.QRectF(5.4, 4.6, 13.2, 9.4), 1.2, 1.2)
    p.drawLine(QtCore.QLineF(2.8, 17.2, 21.2, 17.2))
    p.drawLine(QtCore.QLineF(5.2, 17.2, 6.6, 14.9))
    p.drawLine(QtCore.QLineF(18.8, 17.2, 17.4, 14.9))
    p.drawLine(QtCore.QLineF(10.6, 17.2, 13.4, 17.2))


_PAINTERS = {
    "overview": _draw_overview,
    "cpu": _draw_cpu,
    "memory": _draw_memory,
    "storage": _draw_storage,
    "battery": _draw_battery,
    "network": _draw_network,
    "thermals": _draw_thermals,
    "gpu": _draw_gpu,
    "power": _draw_power,
    "system": _draw_system,
    "fan": _draw_fan,
    "pause": _draw_pause,
    "resume": _draw_resume,
    "refresh": _draw_refresh,
    "copy": _draw_copy,
    "laptop": _draw_laptop,
}


class _VectorEngine(QtGui.QIconEngine):
    """Vector engine: scales the 24-grid to any rect with palette colors."""

    def __init__(self, name: str, palette: QtGui.QPalette, default_size: int):
        super().__init__()
        self._name = name
        self._palette = palette
        self._default_size = int(default_size)

    def clone(self):
        return _VectorEngine(self._name, QtGui.QPalette(self._palette), self._default_size)

    def key(self):
        return "thinkpad-monitor-vector:%s" % self._name

    def availableSizes(self, mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off):
        return [QtCore.QSize(self._default_size, self._default_size)]

    def actualSize(self, size, mode, state):
        if size.isEmpty():
            return QtCore.QSize(self._default_size, self._default_size)
        return QtCore.QSize(size)

    def paint(self, painter, rect, mode, state):
        if painter is None or rect.isEmpty():
            return
        color = _mode_color(self._palette, mode)
        painter.save()
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            side = min(rect.width(), rect.height())
            if side <= 0:
                return
            scale = side / GRID
            dx = rect.x() + (rect.width() - side) / 2.0
            dy = rect.y() + (rect.height() - side) / 2.0
            painter.translate(dx, dy)
            painter.scale(scale, scale)
            painter.setPen(_base_pen(color))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            fn = _PAINTERS.get(self._name)
            if fn is not None:
                fn(painter, color)
        finally:
            painter.restore()

    def pixmap(self, size, mode, state):
        if size.isEmpty():
            return QtGui.QPixmap()
        pm = QtGui.QPixmap(size)
        pm.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pm)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            self.paint(
                painter, QtCore.QRect(0, 0, size.width(), size.height()), mode, state
            )
        finally:
            painter.end()
        return pm

    def scaledPixmap(self, size, mode, state, scale):
        if size.isEmpty() or scale <= 0:
            return QtGui.QPixmap()
        w = max(1, int(round(size.width() * scale)))
        h = max(1, int(round(size.height() * scale)))
        pm = QtGui.QPixmap(w, h)
        pm.setDevicePixelRatio(scale)
        pm.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pm)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            self.paint(
                painter, QtCore.QRect(0, 0, size.width(), size.height()), mode, state
            )
        finally:
            painter.end()
        return pm


def icon(name, palette=None, size: int = 20) -> QtGui.QIcon:
    """Return a crisp native QIcon for *name*.

    Args:
        name: one of ICON_NAMES (case-insensitive, ``-``/``_`` tolerant).
        palette: QPalette used for Normal (Text) / Selected (HighlightedText)
            / Disabled (disabled Text) modes. Defaults to app palette.
        size: default square size (>0) reported via availableSizes().
    """

    key = _normalize(name)
    if key not in _PAINTERS:
        raise ValueError("unknown icon %r; expected one of %s" % (name, ", ".join(ICON_NAMES)))
    try:
        default_size = int(size)
    except (TypeError, ValueError):
        raise ValueError("size must be a positive int")
    if default_size <= 0:
        raise ValueError("size must be a positive int")
    pal = _resolve_palette(palette)
    engine = _VectorEngine(key, pal, default_size)
    return QtGui.QIcon(engine)
