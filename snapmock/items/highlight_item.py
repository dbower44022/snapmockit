"""HighlightItem — semi-transparent wide stroke annotation.

Blur, Highlighter & Eyedropper PRD Section 3: the stroke colour is the highlight colour
(``#FFFF00CC`` by default), whose alpha is the primary opacity (3.7); the width is 24 px
in the 10 to 80 range; the cap is Flat by default (3.4) so the band has a clean marker
edge; the blend mode is Multiply by default, applied as the painter composition mode for
the stroke through the base class, and the shadow, when enabled, is drawn first with
normal composition (3.7).

The stroke is a list of points under ``path_points`` (5.2), smoothed while it is drawn and
simplified on release (3.2; freeform blur decision 2, option A). ``auto_straighten``,
``straighten_threshold``, and ``snap_to_axis`` (3.4) are carried on the item and written to
the file, but they act while the stroke is drawn and never retroactively (3.6): the tool
reads them at the moment of the release.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker

from snapmock.config.constants import (
    DEFAULT_HIGHLIGHT_BLEND_MODE,
    DEFAULT_HIGHLIGHT_COLOR,
    DEFAULT_HIGHLIGHT_WIDTH,
    DEFAULT_STRAIGHTEN_THRESHOLD,
    STRAIGHTEN_THRESHOLD_MAX,
    STRAIGHTEN_THRESHOLD_MIN,
    StrokeCap,
)
from snapmock.items.vector_item import VectorItem


def _point(raw: object) -> QPointF | None:
    """One serialized point, in the ``{"x": …, "y": …}`` form of 5.2 or the older pair."""
    if isinstance(raw, dict):
        return QPointF(float(raw.get("x", 0.0)), float(raw.get("y", 0.0)))
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return QPointF(float(raw[0]), float(raw[1]))
    return None


class HighlightItem(VectorItem):
    """A semi-transparent wide-stroke path used as a highlighter."""

    def __init__(self, parent: VectorItem | None = None) -> None:
        super().__init__(parent)
        self._stroke_color = QColor(DEFAULT_HIGHLIGHT_COLOR)
        self._stroke_width = DEFAULT_HIGHLIGHT_WIDTH
        self._stroke_cap = StrokeCap.FLAT
        self._blend_mode = DEFAULT_HIGHLIGHT_BLEND_MODE
        self._path = QPainterPath()
        self._points: list[tuple[float, float]] = []
        self._auto_straighten = True
        self._straighten_threshold = DEFAULT_STRAIGHTEN_THRESHOLD
        self._snap_to_axis = True

    @property
    def highlight_color(self) -> QColor:
        """The Blur PRD's name for the stroke colour (3.4); the same value."""
        return QColor(self._stroke_color)

    @highlight_color.setter
    def highlight_color(self, value: QColor) -> None:
        self.stroke_color = value

    @property
    def points(self) -> list[tuple[float, float]]:
        """The stroke's points as pairs, the form the older files and walks use."""
        return list(self._points)

    @property
    def path_points(self) -> list[QPointF]:
        """The stroke's points (5.2), after smoothing and straightening."""
        return [QPointF(x, y) for x, y in self._points]

    @path_points.setter
    def path_points(self, value: list[QPointF]) -> None:
        self.set_points([(p.x(), p.y()) for p in value])

    @property
    def is_straight(self) -> bool:
        """Whether the stroke was straightened: two points and nothing between (3.6)."""
        return len(self._points) == 2

    @property
    def auto_straighten(self) -> bool:
        """Whether an approximately straight stroke becomes a line on release (3.4)."""
        return self._auto_straighten

    @auto_straighten.setter
    def auto_straighten(self, value: bool) -> None:
        self._auto_straighten = bool(value)

    @property
    def straighten_threshold(self) -> float:
        """Arc length over straight-line distance, 1.01 to 1.50 (3.4)."""
        return self._straighten_threshold

    @straighten_threshold.setter
    def straighten_threshold(self, value: float) -> None:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            threshold = DEFAULT_STRAIGHTEN_THRESHOLD
        self._straighten_threshold = max(
            STRAIGHTEN_THRESHOLD_MIN, min(STRAIGHTEN_THRESHOLD_MAX, threshold)
        )

    @property
    def snap_to_axis(self) -> bool:
        """Whether a straightened stroke near an axis snaps to it (3.4)."""
        return self._snap_to_axis

    @snap_to_axis.setter
    def snap_to_axis(self, value: bool) -> None:
        self._snap_to_axis = bool(value)

    def add_point(self, x: float, y: float) -> None:
        self.prepareGeometryChange()
        self._points.append((x, y))
        if len(self._points) == 1:
            self._path.moveTo(x, y)
        else:
            self._path.lineTo(x, y)
        self.update()

    def set_points(self, points: list[tuple[float, float]]) -> None:
        """Replace the whole stroke, as the smoothing and the straightening do (3.2, 3.3)."""
        self.prepareGeometryChange()
        self._points = [(float(x), float(y)) for x, y in points]
        self._rebuild_path()
        self.update()

    def _rebuild_path(self) -> None:
        self._path = QPainterPath()
        if self._points:
            self._path.moveTo(self._points[0][0], self._points[0][1])
            for x, y in self._points[1:]:
                self._path.lineTo(x, y)

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._points = [(x * sx, y * sy) for x, y in self._points]
        self._rebuild_path()

    def boundingRect(self) -> QRectF:
        margin = self.stroke_margin() + 2.0
        body = self._path.boundingRect().adjusted(-margin, -margin, margin, margin)
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return self._path.boundingRect()

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self._stroke_width + 4)
        return stroker.createStroke(self._path)

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        self.paint_shadow(painter, self.shadow_path(self._path, closed=False))
        painter.setPen(self.pen())
        painter.drawPath(self._path)
        self._end_flip(painter)

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        if "auto_straighten" in defaults:
            self.auto_straighten = bool(defaults["auto_straighten"])
        if "straighten_threshold" in defaults:
            self.straighten_threshold = defaults["straighten_threshold"]
        if "snap_to_axis" in defaults:
            self.snap_to_axis = bool(defaults["snap_to_axis"])

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "HighlightItem"
        data["path_points"] = [{"x": x, "y": y} for x, y in self._points]
        data["auto_straighten"] = self._auto_straighten
        data["straighten_threshold"] = self._straighten_threshold
        data["snap_to_axis"] = self._snap_to_axis
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> HighlightItem:
        item = cls()
        item._apply_base_data(data)
        # 5.2 names path_points; files saved before this work carry points as pairs
        raw_points = data.get("path_points")
        if not isinstance(raw_points, list):
            raw_points = data.get("points", [])
        points = [p for p in (_point(entry) for entry in raw_points) if p is not None]
        item.set_points([(p.x(), p.y()) for p in points])
        if "auto_straighten" in data:
            item.auto_straighten = bool(data["auto_straighten"])
        if "straighten_threshold" in data:
            item.straighten_threshold = data["straighten_threshold"]
        if "snap_to_axis" in data:
            item.snap_to_axis = bool(data["snap_to_axis"])
        return item
