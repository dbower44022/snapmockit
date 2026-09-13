"""Canvas cursors of General UI PRD 6.6 that Qt does not provide, drawn from the icon set.

Each cursor is a 24 px pixmap with a white halo under a black glyph so it reads on
any canvas content, and a hotspot on the point the glyph indicates. The glyph
cursors reuse the vendored Tabler files under ``resources/icons/tabler/``; the
raster-selection, numbered-step, brush, marker-tip, text-hover, dot-crosshair, and
brush-tip cursors are drawn here because no glyph matches.
Cursors are built on first use (a QCursor needs the application) and cached.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtSvg import QSvgRenderer

from snapmock.core.theme_manager import ICONS_DIR, current_theme

CURSOR_SIZE = 24
_GLYPH_STROKE = 2
_HALO_STROKE = 4
_GLYPH = QColor(0, 0, 0)
_HALO = QColor(255, 255, 255)

_cache: dict[str, QCursor] = {}


def _render_glyph(svg: str, color: QColor, stroke: int, pixmap: QPixmap) -> None:
    data = svg.replace("currentColor", color.name(QColor.NameFormat.HexRgb)).replace(
        f'stroke-width="{_GLYPH_STROKE}"', f'stroke-width="{stroke}"'
    )
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(data.encode("utf-8")).render(painter)
    painter.end()


def glyph_cursor(name: str, hot_x: int, hot_y: int) -> QCursor:
    """The Tabler glyph *name* as a cursor with its hotspot at (*hot_x*, *hot_y*)."""
    cached = _cache.get(name)
    if cached is not None:
        return cached
    try:
        svg = (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")
    except OSError:
        cursor = QCursor(Qt.CursorShape.CrossCursor)
        _cache[name] = cursor
        return cursor
    pixmap = QPixmap(CURSOR_SIZE, CURSOR_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    _render_glyph(svg, _HALO, _HALO_STROKE, pixmap)
    _render_glyph(svg, _GLYPH, _GLYPH_STROKE, pixmap)
    cursor = QCursor(pixmap, hot_x, hot_y)
    _cache[name] = cursor
    return cursor


def rotate_cursor() -> QCursor:
    """Circular arrow over the rotate handle."""
    return glyph_cursor("rotate-clockwise", CURSOR_SIZE // 2, CURSOR_SIZE // 2)


def zoom_in_cursor() -> QCursor:
    """Magnifying glass with a plus; the hotspot is the lens centre."""
    return glyph_cursor("zoom-in", 10, 10)


def zoom_out_cursor() -> QCursor:
    """Magnifying glass with a minus (Zoom tool with Alt held)."""
    return glyph_cursor("zoom-out", 10, 10)


def eyedropper_cursor() -> QCursor:
    """The dropper glyph; the hotspot is its tip at the lower left."""
    return glyph_cursor("color-picker", 4, 20)


def _halo_pen(width: int) -> QPen:
    pen = QPen(_HALO, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def raster_select_cursor() -> QCursor:
    """Crosshair with a dotted square at the lower right (Raster Selection tool)."""
    cached = _cache.get("raster-select")
    if cached is not None:
        return cached
    size = CURSOR_SIZE
    mid = size // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    square = QRect(mid + 3, mid + 3, 8, 8)
    for pen in (_halo_pen(3), QPen(_GLYPH, 1)):
        painter.setPen(pen)
        painter.drawLine(mid, 1, mid, mid - 3)
        painter.drawLine(mid, mid + 3, mid, size - 2)
        painter.drawLine(1, mid, mid - 3, mid)
        painter.drawLine(mid + 3, mid, size - 2, mid)
    painter.setPen(_halo_pen(3))
    painter.drawRect(square)
    dotted = QPen(_GLYPH, 1, Qt.PenStyle.DotLine)
    painter.setPen(dotted)
    painter.drawRect(square)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache["raster-select"] = cursor
    return cursor


def numbered_step_cursor() -> QCursor:
    """Crosshair with a small badge at the lower right (Numbered Step tool, PRD 2.1)."""
    cached = _cache.get("numbered-step")
    if cached is not None:
        return cached
    size = CURSOR_SIZE
    mid = size // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    for pen in (_halo_pen(3), QPen(_GLYPH, 1)):
        painter.setPen(pen)
        painter.drawLine(mid, 1, mid, mid - 3)
        painter.drawLine(mid, mid + 3, mid, size - 2)
        painter.drawLine(1, mid, mid - 3, mid)
        painter.drawLine(mid + 3, mid, size - 2, mid)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    badge = QRect(mid + 3, mid + 3, 9, 9)
    painter.setPen(_halo_pen(2))
    painter.setBrush(QColor(204, 0, 0))
    painter.drawEllipse(badge)
    painter.setPen(QPen(_HALO, 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(mid + 7, mid + 5, mid + 7, mid + 10)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache["numbered-step"] = cursor
    return cursor


def preview_cursor(key: str, preview: QPixmap | None) -> QCursor:
    """Crosshair with a 24 px *preview* at the lower right (Stamp and Emoji tools; kickoff
    silence 8); the plain crosshair when *preview* is None. Cached by *key*."""
    if preview is None or preview.isNull():
        return QCursor(Qt.CursorShape.CrossCursor)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    size = CURSOR_SIZE * 2
    mid = CURSOR_SIZE // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    for pen in (_halo_pen(3), QPen(_GLYPH, 1)):
        painter.setPen(pen)
        painter.drawLine(mid, 1, mid, mid - 3)
        painter.drawLine(mid, mid + 3, mid, CURSOR_SIZE - 2)
        painter.drawLine(1, mid, mid - 3, mid)
        painter.drawLine(mid + 3, mid, CURSOR_SIZE - 2, mid)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    scaled = preview.scaled(
        CURSOR_SIZE,
        CURSOR_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawPixmap(mid + 4, mid + 4, scaled)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache[key] = cursor
    return cursor


BRUSH_CURSOR_MAX = 128
"""A brush cursor never grows past this many screen pixels, so it stays a cursor."""


def brush_cursor(diameter: int) -> QCursor:
    """A circle *diameter* screen pixels across, the Blur tool's brush (Blur PRD 2.6).

    The outline is black over a white halo with a centre dot, so the size reads on any
    canvas content; the hotspot is the centre. A brush wider than
    :data:`BRUSH_CURSOR_MAX` draws at that size, since a cursor cannot grow without end.
    """
    size = max(4, min(int(diameter), BRUSH_CURSOR_MAX))
    key = f"brush-{size}"
    cached = _cache.get(key)
    if cached is not None:
        return cached
    extent = size + 6
    mid = extent // 2
    pixmap = QPixmap(extent, extent)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    radius = size / 2.0
    centre = QPointF(mid, mid)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_halo_pen(3))
    painter.drawEllipse(centre, radius, radius)
    painter.setPen(QPen(_GLYPH, 1))
    painter.drawEllipse(centre, radius, radius)
    painter.setPen(_halo_pen(3))
    painter.drawPoint(centre)
    painter.setPen(QPen(_GLYPH, 1))
    painter.drawPoint(centre)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache[key] = cursor
    return cursor


def dot_crosshair_cursor() -> QCursor:
    """The Freehand / Pen tool's idle cursor, "Crosshair, small dot variant" (Basic Shape
    PRD 9.1): the gapped crosshair with a dot at its centre; the hotspot is the dot."""
    cached = _cache.get("dot-crosshair")
    if cached is not None:
        return cached
    size = CURSOR_SIZE
    mid = size // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    for pen in (_halo_pen(3), QPen(_GLYPH, 1)):
        painter.setPen(pen)
        painter.drawLine(mid, 1, mid, mid - 4)
        painter.drawLine(mid, mid + 4, mid, size - 2)
        painter.drawLine(1, mid, mid - 4, mid)
        painter.drawLine(mid + 4, mid, size - 2, mid)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    centre = QPointF(mid + 0.5, mid + 0.5)
    painter.setPen(_halo_pen(1))
    painter.setBrush(_HALO)
    painter.drawEllipse(centre, 2.0, 2.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_GLYPH)
    painter.drawEllipse(centre, 1.5, 1.5)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache["dot-crosshair"] = cursor
    return cursor


def brush_tip_cursor(diameter: int, color: QColor) -> QCursor:
    """The Freehand / Pen tool's brush tip while a stroke is drawn (Basic Shape PRD 9.2):
    a filled circle *diameter* screen pixels across in *color*, the stroke colour at the
    stroke opacity, over a white halo ring with a black outline so a light colour on a
    light screenshot still reads; the hotspot is the centre.

    Never under 4 px, so a thin stroke still has a tip the eye can find, and never over
    :data:`BRUSH_CURSOR_MAX`, as the Blur tool's brush is. Cached by size and colour.
    """
    size = max(4, min(int(diameter), BRUSH_CURSOR_MAX))
    key = f"brush-tip-{size}-{color.rgba():08x}"
    cached = _cache.get(key)
    if cached is not None:
        return cached
    extent = size + 6
    mid = extent // 2
    pixmap = QPixmap(extent, extent)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    radius = size / 2.0
    centre = QPointF(mid, mid)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_halo_pen(3))
    painter.drawEllipse(centre, radius, radius)
    painter.setPen(QPen(_GLYPH, 1))
    painter.setBrush(QColor(color))
    painter.drawEllipse(centre, radius, radius)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache[key] = cursor
    return cursor


def marker_tip_cursor() -> QCursor:
    """The Highlighter's angled marker tip (Blur PRD 3.1); the hotspot is the tip.

    A chisel tip at the lower left with the barrel running up to the right, drawn black
    over a white halo so it reads on any canvas content.
    """
    cached = _cache.get("marker-tip")
    if cached is not None:
        return cached
    size = CURSOR_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    tip = QPolygonF([QPointF(2, 22), QPointF(6, 14), QPointF(11, 19), QPointF(7, 22)])
    barrel = QPolygonF([QPointF(6, 13), QPointF(14, 3), QPointF(20, 9), QPointF(12, 18)])
    painter.setPen(_halo_pen(3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(tip)
    painter.drawPolygon(barrel)
    painter.setPen(QPen(_GLYPH, 1))
    painter.setBrush(_HALO)
    painter.drawPolygon(barrel)
    painter.setBrush(_GLYPH)
    painter.drawPolygon(tip)
    painter.end()
    cursor = QCursor(pixmap, 2, 22)
    _cache["marker-tip"] = cursor
    return cursor


def text_hover_cursor() -> QCursor:
    """I-beam with an accent highlight bar, shown over an existing text item."""
    cached = _cache.get("text-hover")
    if cached is not None:
        return cached
    size = CURSOR_SIZE
    mid = size // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    accent = QColor(current_theme().accent)
    accent.setAlpha(110)
    painter.fillRect(QRect(mid - 6, 5, 13, size - 10), accent)
    for pen in (_halo_pen(3), QPen(_GLYPH, 1)):
        painter.setPen(pen)
        painter.drawLine(mid, 3, mid, size - 4)
        painter.drawLine(mid - 3, 3, mid + 3, 3)
        painter.drawLine(mid - 3, size - 4, mid + 3, size - 4)
    painter.end()
    cursor = QCursor(pixmap, mid, mid)
    _cache["text-hover"] = cursor
    return cursor


def reset_cursor_cache() -> None:
    """Drop the built cursors (tests, and a theme change for the text-hover accent)."""
    _cache.clear()
