"""PolygonItem — a freeform or regular polygon, a star, or an open polyline (Basic Shape PRD
Section 8).

Freeform: the ordered ``vertices`` the user placed. Regular: ``sides`` vertices on a circle
of ``radius`` around ``center``, the first at ``polygon_rotation`` degrees, alternate
vertices pulled in toward the centre by ``star_indent`` when ``star_enabled``. ``closed``
False draws an open polyline. Fill, stroke, shadow, and hit testing follow the Rectangle
(8.6, 8.7).
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainter, QPainterPath

from snapmock.config.constants import PolygonMode
from snapmock.items.arrow_item import point_from_data, point_to_data
from snapmock.items.vector_item import VectorItem, _enum

SIDES_MIN = 3
SIDES_MAX = 64
STAR_INDENT_MIN = 0.1
STAR_INDENT_MAX = 0.95
MIN_VERTICES = 3
"""A polygon keeps at least three vertices (8.2, 8.5)."""


def regular_vertices(
    center: QPointF,
    radius: float,
    rotation: float,
    sides: int,
    star: bool = False,
    indent: float = 0.5,
) -> list[QPointF]:
    """The vertices of a regular polygon, or of a star with *sides* points (8.6).

    The first vertex sits at *rotation* degrees from the centre. A star alternates the
    outer radius with an inner radius of the outer times ``1 - indent``, so an indent of 0
    is the plain polygon and an indent near 1 brings the inner points to the centre, as
    8.3 describes (8.6's "outer radius times star_indent" reads the other way; notes).
    """
    sides = max(SIDES_MIN, min(SIDES_MAX, int(sides)))
    start = math.radians(rotation)
    if not star:
        return [
            QPointF(
                center.x() + radius * math.cos(start + 2 * math.pi * k / sides),
                center.y() + radius * math.sin(start + 2 * math.pi * k / sides),
            )
            for k in range(sides)
        ]
    inner = radius * (1.0 - indent)
    points = []
    for k in range(2 * sides):
        r = radius if k % 2 == 0 else inner
        angle = start + math.pi * k / sides
        points.append(QPointF(center.x() + r * math.cos(angle), center.y() + r * math.sin(angle)))
    return points


class PolygonItem(VectorItem):
    """A polygon annotation item."""

    def __init__(
        self, vertices: list[QPointF] | None = None, parent: VectorItem | None = None
    ) -> None:
        super().__init__(parent)
        self._vertices: list[QPointF] = [QPointF(v) for v in vertices or []]
        self._polygon_mode: PolygonMode = PolygonMode.FREEFORM
        self._sides: int = 5
        self._center: QPointF | None = None
        self._radius: float | None = None
        self._polygon_rotation: float = -90.0
        self._star_enabled: bool = False
        self._star_indent: float = 0.5
        self._closed: bool = True

    # ------------------------------------------------------------ properties

    @property
    def vertices(self) -> list[QPointF]:
        """The vertices in item coordinates: placed for a freeform polygon, computed for a
        regular one (8.3)."""
        if self._polygon_mode is PolygonMode.REGULAR and self._center is not None:
            return regular_vertices(
                self._center,
                self._radius or 0.0,
                self._polygon_rotation,
                self._sides,
                self._star_enabled,
                self._star_indent,
            )
        return [QPointF(v) for v in self._vertices]

    @vertices.setter
    def vertices(self, value: list[QPointF]) -> None:
        self._vertices = [QPointF(v) for v in value]
        self._geometry_changed()

    def insert_vertex(self, index: int, position: QPointF) -> None:
        """Insert *position* before the vertex at *index* (8.5; ``InsertVertexCommand``)."""
        self._vertices.insert(index, QPointF(position))
        self._geometry_changed()

    def remove_vertex(self, index: int) -> QPointF:
        """Remove and return the vertex at *index* (8.5; ``RemoveVertexCommand``)."""
        vertex = self._vertices.pop(index)
        self._geometry_changed()
        return vertex

    @property
    def polygon_mode(self) -> PolygonMode:
        return self._polygon_mode

    @polygon_mode.setter
    def polygon_mode(self, value: PolygonMode) -> None:
        self._polygon_mode = PolygonMode(value)
        self._geometry_changed()

    @property
    def sides(self) -> int:
        return self._sides

    @sides.setter
    def sides(self, value: int) -> None:
        self._sides = max(SIDES_MIN, min(SIDES_MAX, int(value)))
        self._geometry_changed()

    @property
    def center(self) -> QPointF | None:
        return None if self._center is None else QPointF(self._center)

    @center.setter
    def center(self, value: QPointF | None) -> None:
        self._center = None if value is None else QPointF(value)
        self._geometry_changed()

    @property
    def radius(self) -> float | None:
        return self._radius

    @radius.setter
    def radius(self, value: float | None) -> None:
        self._radius = None if value is None else max(0.0, float(value))
        self._geometry_changed()

    @property
    def polygon_rotation(self) -> float:
        """The first vertex's angle in degrees for a regular polygon (10.6's ``rotation``,
        renamed because the item's own rotation already takes that name)."""
        return self._polygon_rotation

    @polygon_rotation.setter
    def polygon_rotation(self, value: float) -> None:
        self._polygon_rotation = float(value)
        self._geometry_changed()

    @property
    def regular_geometry(self) -> tuple[QPointF | None, float | None, float]:
        """The centre, the radius, and the rotation together: what a regular polygon's
        point edits change (8.5)."""
        return (self.center, self._radius, self._polygon_rotation)

    @regular_geometry.setter
    def regular_geometry(self, value: tuple[QPointF | None, float | None, float]) -> None:
        center, radius, rotation = value
        self._center = None if center is None else QPointF(center)
        self._radius = None if radius is None else max(0.0, float(radius))
        self._polygon_rotation = float(rotation)
        self._geometry_changed()

    @property
    def star_enabled(self) -> bool:
        return self._star_enabled

    @star_enabled.setter
    def star_enabled(self, value: bool) -> None:
        self._star_enabled = bool(value)
        self._geometry_changed()

    @property
    def star_indent(self) -> float:
        return self._star_indent

    @star_indent.setter
    def star_indent(self, value: float) -> None:
        self._star_indent = max(STAR_INDENT_MIN, min(STAR_INDENT_MAX, float(value)))
        self._geometry_changed()

    @property
    def closed(self) -> bool:
        """False draws an open polyline (8.3)."""
        return self._closed

    @closed.setter
    def closed(self, value: bool) -> None:
        self._closed = bool(value)
        self._geometry_changed()

    # ------------------------------------------------------------ geometry

    def outline(self) -> QPainterPath:
        """The polygon's edge: ``moveTo`` the first vertex, ``lineTo`` the rest, closed
        unless the polygon is an open polyline (8.6)."""
        path = QPainterPath()
        vertices = self.vertices
        if not vertices:
            return path
        path.moveTo(vertices[0])
        for vertex in vertices[1:]:
            path.lineTo(vertex)
        if self._closed and len(vertices) > 2:
            path.closeSubpath()
        return path

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._vertices = [QPointF(v.x() * sx, v.y() * sy) for v in self._vertices]
        if self._center is not None:
            self._center = QPointF(self._center.x() * sx, self._center.y() * sy)
        if self._radius is not None:
            self._radius *= (sx + sy) / 2.0

    def boundingRect(self) -> QRectF:
        margin = self.stroke_margin() + 2.0
        body = self.outline().boundingRect().adjusted(-margin, -margin, margin, margin)
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return self.outline().boundingRect()

    def shape(self) -> QPainterPath:
        """The filled polygon when the fill is not transparent, else a band around the
        outline, the Rectangle's rule (8.7)."""
        if not self._closed:
            from PyQt6.QtGui import QPainterPathStroker

            stroker = QPainterPathStroker()
            stroker.setWidth(self._stroke_width + self.HIT_PADDING)
            return stroker.createStroke(self.outline())
        return self.hit_shape(self.outline())

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        outline = self.outline()
        self.paint_shadow(painter, self.shadow_path(outline, closed=self._closed))
        painter.setPen(self.pen())
        if self._closed:
            painter.setBrush(self.brush())
        else:
            from PyQt6.QtCore import Qt

            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)
        self._end_flip(painter)

    # ------------------------------------------------------------ creation defaults

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        mode = defaults.get("polygon_mode")
        if isinstance(mode, PolygonMode):
            self._polygon_mode = mode
        if "sides" in defaults:
            self._sides = max(SIDES_MIN, min(SIDES_MAX, int(defaults["sides"])))
        if "star_enabled" in defaults:
            self._star_enabled = bool(defaults["star_enabled"])
        if "star_indent" in defaults:
            self._star_indent = max(
                STAR_INDENT_MIN, min(STAR_INDENT_MAX, float(defaults["star_indent"]))
            )
        if "closed" in defaults:
            self._closed = bool(defaults["closed"])
        self._geometry_changed()

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "PolygonItem"
        data["vertices"] = [point_to_data(v) for v in self.vertices]
        data["polygon_mode"] = self._polygon_mode.value
        data["sides"] = self._sides
        data["center"] = point_to_data(self._center)
        data["radius"] = self._radius
        data["polygon_rotation"] = self._polygon_rotation
        data["star_enabled"] = self._star_enabled
        data["star_indent"] = self._star_indent
        data["closed"] = self._closed
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> PolygonItem:
        raw = data.get("vertices", [])
        vertices = [p for p in (point_from_data(v) for v in raw or []) if p is not None]
        item = cls(vertices=vertices)
        item._apply_base_data(data)
        item._polygon_mode = _enum(PolygonMode, data.get("polygon_mode"), PolygonMode.FREEFORM)
        item._sides = max(SIDES_MIN, min(SIDES_MAX, int(data.get("sides", 5))))
        item._center = point_from_data(data.get("center"))
        radius = data.get("radius")
        item._radius = None if radius is None else max(0.0, float(radius))
        item._polygon_rotation = float(data.get("polygon_rotation", -90.0))
        item._star_enabled = bool(data.get("star_enabled", False))
        item._star_indent = max(
            STAR_INDENT_MIN, min(STAR_INDENT_MAX, float(data.get("star_indent", 0.5)))
        )
        item._closed = bool(data.get("closed", True))
        if item._polygon_mode is PolygonMode.REGULAR and item._center is None:
            item._polygon_mode = PolygonMode.FREEFORM  # the vertices still draw it
        return item
