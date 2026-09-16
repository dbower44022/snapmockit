"""ArcItem — a curved arc segment (Basic Shape PRD Section 7).

A quadratic Bezier from ``start_point`` through ``control_point`` to ``end_point`` (7.6),
drawn Open (the curve alone), Chord (closed by a straight line from the end back to the
start), or Pie (closed by two lines through the centre of the circle the arc belongs to),
the closed types filled with the fill colour. The optional heads are the Arrow's
(``head_geometry``, 4.4), oriented along the tangent at each end.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QPainter, QPainterPath, QPainterPathStroker, QPen

from snapmock.config.constants import HEAD_SIZE_PX, ArcType, HeadSize, HeadStyle
from snapmock.items.arrow_item import head_geometry, point_from_data, point_to_data, quad_shaft
from snapmock.items.vector_item import VectorItem, _enum, with_alpha

_EPSILON = 1e-9


def _unit(dx: float, dy: float, default: QPointF) -> QPointF:
    length = math.hypot(dx, dy)
    if length <= _EPSILON:
        return QPointF(default)
    return QPointF(dx / length, dy / length)


def circumcentre(a: QPointF, b: QPointF, c: QPointF) -> QPointF | None:
    """The centre of the circle through *a*, *b*, and *c*; None when they are in line."""
    d = 2.0 * (a.x() * (b.y() - c.y()) + b.x() * (c.y() - a.y()) + c.x() * (a.y() - b.y()))
    if abs(d) < 1e-6:
        return None
    a2 = a.x() ** 2 + a.y() ** 2
    b2 = b.x() ** 2 + b.y() ** 2
    c2 = c.x() ** 2 + c.y() ** 2
    x = (a2 * (b.y() - c.y()) + b2 * (c.y() - a.y()) + c2 * (a.y() - b.y())) / d
    y = (a2 * (c.x() - b.x()) + b2 * (a.x() - c.x()) + c2 * (b.x() - a.x())) / d
    return QPointF(x, y)


class ArcItem(VectorItem):
    """An arc between two points, bent through a control point."""

    def __init__(
        self,
        start: QPointF | None = None,
        end: QPointF | None = None,
        control: QPointF | None = None,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._start = QPointF(start) if start is not None else QPointF(0, 0)
        self._end = QPointF(end) if end is not None else QPointF(100, 0)
        self._control = (
            QPointF(control)
            if control is not None
            else QPointF(
                (self._start.x() + self._end.x()) / 2, (self._start.y() + self._end.y()) / 2
            )
        )
        self._arc_type: ArcType = ArcType.OPEN
        self._head_style: HeadStyle = HeadStyle.NONE
        self._tail_style: HeadStyle = HeadStyle.NONE
        self._head_size: HeadSize = HeadSize.MEDIUM

    # ------------------------------------------------------------ properties

    @property
    def start_point(self) -> QPointF:
        return QPointF(self._start)

    @start_point.setter
    def start_point(self, value: QPointF) -> None:
        self._start = QPointF(value)
        self._geometry_changed()

    @property
    def end_point(self) -> QPointF:
        return QPointF(self._end)

    @end_point.setter
    def end_point(self, value: QPointF) -> None:
        self._end = QPointF(value)
        self._geometry_changed()

    @property
    def control_point(self) -> QPointF:
        """The Bezier control point that sets the curvature (7.3)."""
        return QPointF(self._control)

    @control_point.setter
    def control_point(self, value: QPointF) -> None:
        self._control = QPointF(value)
        self._geometry_changed()

    @property
    def arc_type(self) -> ArcType:
        """Open, Chord, or Pie (7.3)."""
        return self._arc_type

    @arc_type.setter
    def arc_type(self, value: ArcType) -> None:
        self._arc_type = ArcType(value)
        self._geometry_changed()

    @property
    def head_style(self) -> HeadStyle:
        return self._head_style

    @head_style.setter
    def head_style(self, value: HeadStyle) -> None:
        self._head_style = HeadStyle(value)
        self._geometry_changed()

    @property
    def tail_style(self) -> HeadStyle:
        return self._tail_style

    @tail_style.setter
    def tail_style(self, value: HeadStyle) -> None:
        self._tail_style = HeadStyle(value)
        self._geometry_changed()

    @property
    def head_size(self) -> HeadSize:
        return self._head_size

    @head_size.setter
    def head_size(self, value: HeadSize) -> None:
        self._head_size = HeadSize(value)
        self._geometry_changed()

    def effective_head_size(self) -> float:
        """The named size plus the stroke width, the Arrow's rule (4.3)."""
        return HEAD_SIZE_PX[self._head_size] + self._stroke_width

    # ------------------------------------------------------------ geometry

    def peak(self) -> QPointF:
        """The curve at its middle parameter: the point the bulge is measured to (7.2)."""
        return QPointF(
            0.25 * self._start.x() + 0.5 * self._control.x() + 0.25 * self._end.x(),
            0.25 * self._start.y() + 0.5 * self._control.y() + 0.25 * self._end.y(),
        )

    def virtual_centre(self) -> QPointF | None:
        """The centre of the circle through the two ends and the peak, where a Pie's lines
        meet (7.6); None while the arc is straight."""
        return circumcentre(self._start, self.peak(), self._end)

    def curve_path(self) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(self._start)
        path.quadTo(self._control, self._end)
        return path

    def closing_path(self) -> QPainterPath:
        """The straight lines that close a Chord or a Pie, from the end back to the start;
        empty for an Open arc. A straight Pie closes as a Chord."""
        path = QPainterPath()
        if self._arc_type is ArcType.OPEN:
            return path
        path.moveTo(self._end)
        centre = self.virtual_centre() if self._arc_type is ArcType.PIE else None
        if centre is not None:
            path.lineTo(centre)
        path.lineTo(self._start)
        return path

    def outline(self) -> QPainterPath:
        """The curve, closed by the chord or the pie's lines for those types."""
        path = self.curve_path()
        if self._arc_type is ArcType.OPEN:
            return path
        centre = self.virtual_centre() if self._arc_type is ArcType.PIE else None
        if centre is not None:
            path.lineTo(centre)
        path.closeSubpath()
        return path

    def end_directions(self) -> tuple[QPointF, QPointF]:
        """The head's direction at the end point and the tail's at the start point: the
        tangent of the curve at each end (7.6)."""
        chord = _unit(
            self._end.x() - self._start.x(), self._end.y() - self._start.y(), QPointF(1, 0)
        )
        back = QPointF(-chord.x(), -chord.y())
        c = self._control
        head_from = (
            c
            if math.hypot(c.x() - self._end.x(), c.y() - self._end.y()) > _EPSILON
            else self._start
        )
        tail_from = (
            c
            if math.hypot(c.x() - self._start.x(), c.y() - self._start.y()) > _EPSILON
            else self._end
        )
        head = _unit(self._end.x() - head_from.x(), self._end.y() - head_from.y(), chord)
        tail = _unit(self._start.x() - tail_from.x(), self._start.y() - tail_from.y(), back)
        return head, tail

    def head_paths(self) -> tuple[QPainterPath, QPainterPath, QPainterPath]:
        """The filled heads, the open heads' lines, and the curve between them."""
        size = self.effective_head_size()
        head_dir, tail_dir = self.end_directions()
        head_fill, head_lines, head_retreat = head_geometry(
            self._end, head_dir, self._head_style, size
        )
        tail_fill, tail_lines, tail_retreat = head_geometry(
            self._start, tail_dir, self._tail_style, size
        )
        filled = QPainterPath(head_fill)
        filled.addPath(tail_fill)
        lines = QPainterPath(head_lines)
        lines.addPath(tail_lines)
        shaft = quad_shaft(self._start, self._control, self._end, tail_retreat, head_retreat)
        return filled, lines, shaft

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._start = QPointF(self._start.x() * sx, self._start.y() * sy)
        self._end = QPointF(self._end.x() * sx, self._end.y() * sy)
        self._control = QPointF(self._control.x() * sx, self._control.y() * sy)

    def boundingRect(self) -> QRectF:
        margin = self.effective_head_size() + self._stroke_width + 4
        body = (
            self.outline()
            .boundingRect()
            .united(QRectF(self._start, self._end).normalized())
            .adjusted(-margin, -margin, margin, margin)
        )
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return self.outline().boundingRect().united(QRectF(self._start, self._end).normalized())

    def shape(self) -> QPainterPath:
        """A band around the outline, stroke width plus 4 px; the whole inside of a filled
        Chord or Pie (the Rectangle's rule, 5.6); the heads."""
        outline = self.outline()
        stroker = QPainterPathStroker()
        stroker.setWidth(self._stroke_width + self.HIT_PADDING)
        area = stroker.createStroke(outline)
        if self._arc_type is not ArcType.OPEN and self._fill_color.alpha() > 0:
            area = area.united(outline)
        filled, lines, _shaft = self.head_paths()
        area.addPath(filled)
        if not lines.isEmpty():
            area.addPath(stroker.createStroke(lines))
        return area

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        closed = self._arc_type is not ArcType.OPEN
        filled, lines, shaft = self.head_paths()
        closing = self.closing_path()
        outline = self.outline()
        shadow = self.shadow_path(outline if closed else shaft, closed=closed)
        if not filled.isEmpty():
            shadow = shadow.united(filled.united(self.stroke_outline(filled)))
        if not lines.isEmpty():
            shadow = shadow.united(self.stroke_outline(lines))
        self.paint_shadow(painter, shadow)
        if closed:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.brush())
            painter.drawPath(outline)
        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if shaft.length() > 0.0:
            painter.drawPath(shaft)
        if not closing.isEmpty():
            painter.drawPath(closing)
        if not lines.isEmpty():
            open_pen = QPen(pen)
            open_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            open_pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(open_pen)
            painter.drawPath(lines)
        if not filled.isEmpty():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(with_alpha(self._stroke_color, self._stroke_opacity)))
            painter.drawPath(filled)
        self._end_flip(painter)

    # ------------------------------------------------------------ creation defaults

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        arc_type = defaults.get("arc_type")
        if isinstance(arc_type, ArcType):
            self._arc_type = arc_type
        head = defaults.get("head_style")
        if isinstance(head, HeadStyle):
            self._head_style = head
        tail = defaults.get("tail_style")
        if isinstance(tail, HeadStyle):
            self._tail_style = tail
        size = defaults.get("head_size")
        if isinstance(size, HeadSize):
            self._head_size = size
        self._geometry_changed()

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "ArcItem"
        data["start_point"] = point_to_data(self._start)
        data["end_point"] = point_to_data(self._end)
        data["control_point"] = point_to_data(self._control)
        data["arc_type"] = self._arc_type.value
        data["head_style"] = self._head_style.value
        data["tail_style"] = self._tail_style.value
        data["head_size"] = self._head_size.value
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> ArcItem:
        start = point_from_data(data.get("start_point")) or QPointF(0, 0)
        end = point_from_data(data.get("end_point")) or QPointF(100, 0)
        control = point_from_data(data.get("control_point"))
        item = cls(start=start, end=end, control=control)
        item._apply_base_data(data)
        item._arc_type = _enum(ArcType, data.get("arc_type"), ArcType.OPEN)
        item._head_style = _enum(HeadStyle, data.get("head_style"), HeadStyle.NONE)
        item._tail_style = _enum(HeadStyle, data.get("tail_style"), HeadStyle.NONE)
        item._head_size = _enum(HeadSize, data.get("head_size"), HeadSize.MEDIUM)
        return item
