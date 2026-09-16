"""ArrowItem — line with arrowhead annotation.

Basic Shape Annotation Tools PRD Section 4: a shaft from the tail (``p1``) to the head
(``p2``) with a head style and a tail style from the six of 4.3 (None, Open, Filled,
Diamond, Circle, Square), a head size from the four named sizes or a custom size, all
painted per 4.4: an open head is two stroked lines at 30 degrees with a round cap; the
filled heads take the stroke colour at the stroke opacity, and the shaft ends at a filled
head's base so nothing overlaps. ``line_style`` draws the shaft Straight, Curved (a
quadratic Bezier through ``control_point``, the midpoint by default, 4.5), or Elbow (two
or three right-angle segments through ``bend_point``, 4.6); the heads orient along the
tangent at each end or along the terminal segment.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF

from snapmock.config.constants import (
    HEAD_SIZE_CUSTOM_MAX,
    HEAD_SIZE_PX,
    HeadSize,
    HeadStyle,
    LineStyle,
)
from snapmock.items.vector_item import VectorItem, _enum, with_alpha

_OPEN_HALF_ANGLE = math.radians(30.0)
_EPSILON = 1e-9


def _unit(dx: float, dy: float, default: QPointF) -> QPointF:
    length = math.hypot(dx, dy)
    if length <= _EPSILON:
        return QPointF(default)
    return QPointF(dx / length, dy / length)


def _quad_at(p0: QPointF, c: QPointF, p2: QPointF, t: float) -> QPointF:
    """The quadratic Bezier through *p0*, *c*, *p2* at *t*."""
    u = 1.0 - t
    return QPointF(
        u * u * p0.x() + 2 * u * t * c.x() + t * t * p2.x(),
        u * u * p0.y() + 2 * u * t * c.y() + t * t * p2.y(),
    )


def _quad_blossom(p0: QPointF, c: QPointF, p2: QPointF, a: float, b: float) -> QPointF:
    """The control point of the piece of the curve between *a* and *b*."""
    w0 = (1 - a) * (1 - b)
    w1 = (1 - a) * b + a * (1 - b)
    w2 = a * b
    return QPointF(w0 * p0.x() + w1 * c.x() + w2 * p2.x(), w0 * p0.y() + w1 * c.y() + w2 * p2.y())


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def point_to_data(point: QPointF | None) -> dict[str, float] | None:
    """The 10.2 form of a nullable point: ``{"x": float, "y": float}`` or null."""
    return None if point is None else {"x": point.x(), "y": point.y()}


def point_from_data(raw: object) -> QPointF | None:
    """A point from its 10.2 form, or from an ``[x, y]`` list; None when absent."""
    if isinstance(raw, dict) and "x" in raw and "y" in raw:
        return QPointF(float(raw["x"]), float(raw["y"]))
    if isinstance(raw, list | tuple) and len(raw) == 2:
        return QPointF(float(raw[0]), float(raw[1]))
    return None


def head_geometry(
    tip: QPointF, forward: QPointF, style: HeadStyle, size: float
) -> tuple[QPainterPath, QPainterPath, float]:
    """The filled path, the open lines path, and how far a shaft retreats from *tip* for
    a head of *style* and *size* pointing along *forward* (Basic Shape PRD 4.4); shared by
    the arrow and the arc (7.3)."""
    u = forward
    v = QPointF(-u.y(), u.x())
    filled = QPainterPath()
    lines = QPainterPath()
    if style is HeadStyle.OPEN:
        length = size
        for sign in (1.0, -1.0):
            end = QPointF(
                tip.x()
                - length
                * (math.cos(_OPEN_HALF_ANGLE) * u.x() + sign * math.sin(_OPEN_HALF_ANGLE) * v.x()),
                tip.y()
                - length
                * (math.cos(_OPEN_HALF_ANGLE) * u.y() + sign * math.sin(_OPEN_HALF_ANGLE) * v.y()),
            )
            lines.moveTo(tip)
            lines.lineTo(end)
        return filled, lines, 0.0
    if style is HeadStyle.FILLED:
        base = QPointF(tip.x() - size * u.x(), tip.y() - size * u.y())
        filled.addPolygon(
            QPolygonF(
                [
                    tip,
                    QPointF(base.x() + size * v.x(), base.y() + size * v.y()),
                    QPointF(base.x() - size * v.x(), base.y() - size * v.y()),
                ]
            )
        )
        filled.closeSubpath()
        return filled, lines, size
    half = size / 2.0
    if style is HeadStyle.DIAMOND:
        filled.addPolygon(
            QPolygonF(
                [
                    QPointF(tip.x() + half * u.x(), tip.y() + half * u.y()),
                    QPointF(tip.x() + half * v.x(), tip.y() + half * v.y()),
                    QPointF(tip.x() - half * u.x(), tip.y() - half * u.y()),
                    QPointF(tip.x() - half * v.x(), tip.y() - half * v.y()),
                ]
            )
        )
        filled.closeSubpath()
        return filled, lines, half
    if style is HeadStyle.CIRCLE:
        filled.addEllipse(tip, half, half)
        return filled, lines, half
    if style is HeadStyle.SQUARE:
        filled.addPolygon(
            QPolygonF(
                [
                    QPointF(tip.x() + half * (u.x() + v.x()), tip.y() + half * (u.y() + v.y())),
                    QPointF(tip.x() + half * (u.x() - v.x()), tip.y() + half * (u.y() - v.y())),
                    QPointF(tip.x() - half * (u.x() + v.x()), tip.y() - half * (u.y() + v.y())),
                    QPointF(tip.x() - half * (u.x() - v.x()), tip.y() - half * (u.y() - v.y())),
                ]
            )
        )
        filled.closeSubpath()
        return filled, lines, half
    return filled, lines, 0.0


class ArrowItem(VectorItem):
    """A line with an arrowhead at the end point and an optional one at the start."""

    def __init__(
        self,
        line: QLineF | None = None,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._line: QLineF = line if line is not None else QLineF(0, 0, 100, 0)
        self._head_style: HeadStyle = HeadStyle.OPEN
        self._tail_style: HeadStyle = HeadStyle.NONE
        self._head_size: HeadSize = HeadSize.MEDIUM
        self._head_size_custom: float = 0.0
        self._line_style: LineStyle = LineStyle.STRAIGHT
        self._control_point: QPointF | None = None
        self._bend_point: QPointF | None = None

    # ------------------------------------------------------------ properties

    @property
    def line(self) -> QLineF:
        return QLineF(self._line)

    @line.setter
    def line(self, value: QLineF) -> None:
        self._line = QLineF(value)
        self._geometry_changed()

    @property
    def head_style(self) -> HeadStyle:
        """The style at the end point (4.3); Open by default."""
        return self._head_style

    @head_style.setter
    def head_style(self, value: HeadStyle) -> None:
        self._head_style = HeadStyle(value)
        self._geometry_changed()

    @property
    def tail_style(self) -> HeadStyle:
        """The style at the start point (4.3); None by default."""
        return self._tail_style

    @tail_style.setter
    def tail_style(self, value: HeadStyle) -> None:
        self._tail_style = HeadStyle(value)
        self._geometry_changed()

    @property
    def head_size(self) -> HeadSize:
        """Small, Medium, Large, or XLarge (4.3); the custom size wins when set."""
        return self._head_size

    @head_size.setter
    def head_size(self, value: HeadSize) -> None:
        self._head_size = HeadSize(value)
        self._geometry_changed()

    @property
    def head_size_custom(self) -> float:
        """A custom size in pixels, 4 to 60; 0 means the named size applies (4.3)."""
        return self._head_size_custom

    @head_size_custom.setter
    def head_size_custom(self, value: float) -> None:
        size = float(value)
        self._head_size_custom = 0.0 if size <= 0 else max(4.0, min(HEAD_SIZE_CUSTOM_MAX, size))
        self._geometry_changed()

    @property
    def line_style(self) -> LineStyle:
        """Straight, Curved (4.5), or Elbow (4.6)."""
        return self._line_style

    @line_style.setter
    def line_style(self, value: LineStyle) -> None:
        self._line_style = LineStyle(value)
        self._geometry_changed()

    @property
    def control_point(self) -> QPointF | None:
        """A curved arrow's Bezier control point in item coordinates; None means the
        midpoint of the line, so a new curved arrow is straight until the point moves."""
        return None if self._control_point is None else QPointF(self._control_point)

    @control_point.setter
    def control_point(self, value: QPointF | None) -> None:
        self._control_point = None if value is None else QPointF(value)
        self._geometry_changed()

    @property
    def bend_point(self) -> QPointF | None:
        """An elbow arrow's bend in item coordinates; its x places the vertical segment.
        None means the midpoint's x (4.6)."""
        return None if self._bend_point is None else QPointF(self._bend_point)

    @bend_point.setter
    def bend_point(self, value: QPointF | None) -> None:
        self._bend_point = None if value is None else QPointF(value)
        self._geometry_changed()

    def effective_head_size(self) -> float:
        """The head's size in pixels: the custom size, else the named size, plus the stroke
        width (4.3: the size scales with the stroke width; the addition is the shipped rule)."""
        base = (
            self._head_size_custom if self._head_size_custom > 0 else HEAD_SIZE_PX[self._head_size]
        )
        return base + self._stroke_width

    # ------------------------------------------------------------ geometry

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._line = QLineF(
            self._line.x1() * sx,
            self._line.y1() * sy,
            self._line.x2() * sx,
            self._line.y2() * sy,
        )
        if self._control_point is not None:
            self._control_point = QPointF(
                self._control_point.x() * sx, self._control_point.y() * sy
            )
        if self._bend_point is not None:
            self._bend_point = QPointF(self._bend_point.x() * sx, self._bend_point.y() * sy)
        if self._head_size_custom > 0:
            self._head_size_custom = max(
                4.0, min(HEAD_SIZE_CUSTOM_MAX, self._head_size_custom * (sx + sy) / 2.0)
            )

    def _direction(self) -> QPointF:
        """The unit vector from the tail to the head; along x for a zero-length line."""
        return _unit(self._line.dx(), self._line.dy(), QPointF(1.0, 0.0))

    def effective_control_point(self) -> QPointF:
        """The control point the curve is drawn through (4.5)."""
        if self._control_point is not None:
            return QPointF(self._control_point)
        return self._line.center()

    def bend_x(self) -> float:
        """The x of an elbow's vertical segment (4.6)."""
        if self._bend_point is not None:
            return self._bend_point.x()
        return (self._line.x1() + self._line.x2()) / 2.0

    def bend_handle_point(self) -> QPointF:
        """Where the bend point's handle sits: the middle of the vertical segment."""
        return QPointF(self.bend_x(), (self._line.y1() + self._line.y2()) / 2.0)

    def elbow_points(self) -> list[QPointF]:
        """The elbow's corners from the tail to the head: horizontal, vertical, horizontal,
        with a zero-length segment dropped, so two or three segments at right angles."""
        p1, p2 = self._line.p1(), self._line.p2()
        x = self.bend_x()
        points = [p1, QPointF(x, p1.y()), QPointF(x, p2.y()), p2]
        kept = [points[0]]
        for point in points[1:]:
            if _distance(point, kept[-1]) > _EPSILON:
                kept.append(point)
        if len(kept) == 1:
            kept.append(QPointF(p2))
        return kept

    def end_directions(self) -> tuple[QPointF, QPointF]:
        """Unit vectors along which the head points at the end point and the tail points
        at the start point: the tangent for a curve (4.5), the terminal segment for an
        elbow (4.6), the line itself when straight."""
        u = self._direction()
        back = QPointF(-u.x(), -u.y())
        p1, p2 = self._line.p1(), self._line.p2()
        if self._line_style is LineStyle.CURVED:
            c = self.effective_control_point()
            head_from = c if _distance(c, p2) > _EPSILON else p1
            tail_from = c if _distance(c, p1) > _EPSILON else p2
            head = _unit(p2.x() - head_from.x(), p2.y() - head_from.y(), u)
            tail = _unit(p1.x() - tail_from.x(), p1.y() - tail_from.y(), back)
            return head, tail
        if self._line_style is LineStyle.ELBOW:
            points = self.elbow_points()
            head = _unit(points[-1].x() - points[-2].x(), points[-1].y() - points[-2].y(), u)
            tail = _unit(points[0].x() - points[1].x(), points[0].y() - points[1].y(), back)
            return head, tail
        return u, back

    def _head_geometry(
        self, tip: QPointF, forward: QPointF, style: HeadStyle
    ) -> tuple[QPainterPath, QPainterPath, float]:
        """The head of *style* at *tip* at this arrow's size (4.4)."""
        return head_geometry(tip, forward, style, self.effective_head_size())

    def head_paths(self) -> tuple[QPainterPath, QPainterPath, QPainterPath]:
        """The filled heads, the open heads' lines, and the shaft that remains between them."""
        head_dir, tail_dir = self.end_directions()
        head_fill, head_lines, head_retreat = self._head_geometry(
            self._line.p2(), head_dir, self._head_style
        )
        tail_fill, tail_lines, tail_retreat = self._head_geometry(
            self._line.p1(), tail_dir, self._tail_style
        )
        filled = head_fill.united(tail_fill) if not tail_fill.isEmpty() else head_fill
        if head_fill.isEmpty():
            filled = tail_fill
        lines = QPainterPath(head_lines)
        lines.addPath(tail_lines)
        return filled, lines, self._shaft_path(tail_retreat, head_retreat)

    def _shaft_path(self, tail_retreat: float, head_retreat: float) -> QPainterPath:
        """The line path with *tail_retreat* taken off the start and *head_retreat* off
        the end, so the shaft stops at a filled head's base."""
        path = QPainterPath()
        if self._line_style is LineStyle.CURVED:
            return quad_shaft(
                self._line.p1(),
                self.effective_control_point(),
                self._line.p2(),
                tail_retreat,
                head_retreat,
            )
        points = (
            self.elbow_points()
            if self._line_style is LineStyle.ELBOW
            else [self._line.p1(), self._line.p2()]
        )
        total = sum(_distance(p, q) for p, q in zip(points, points[1:]))
        head_retreat = min(head_retreat, total)
        tail_retreat = min(tail_retreat, max(0.0, total - head_retreat))
        start = tail_retreat
        end = total - head_retreat
        walked = 0.0
        started = False
        for seg_a, seg_b in zip(points, points[1:]):
            seg = _distance(seg_a, seg_b)
            if seg <= _EPSILON:
                continue
            lo, hi = walked, walked + seg
            walked = hi
            if hi < start or lo > end:
                continue
            t0 = max(0.0, (start - lo) / seg)
            t1 = min(1.0, (end - lo) / seg)
            p_from = QPointF(
                seg_a.x() + (seg_b.x() - seg_a.x()) * t0, seg_a.y() + (seg_b.y() - seg_a.y()) * t0
            )
            p_to = QPointF(
                seg_a.x() + (seg_b.x() - seg_a.x()) * t1, seg_a.y() + (seg_b.y() - seg_a.y()) * t1
            )
            if not started:
                path.moveTo(p_from)
                started = True
            path.lineTo(p_to)
        if not started:
            path.moveTo(self._line.p1())
            path.lineTo(self._line.p1())
        return path

    @staticmethod
    def _curve_parameter(
        p0: QPointF,
        c: QPointF,
        p2: QPointF,
        anchor: QPointF,
        retreat: float,
        low: float,
        high: float,
        *,
        from_end: bool,
    ) -> float:
        """The curve parameter, between *low* and *high*, at *retreat* straight-line
        distance from *anchor*, the end point (*from_end*) or the start point."""
        if retreat <= 0.0:
            return high if from_end else low
        near, far = (high, low) if from_end else (low, high)
        if _distance(_quad_at(p0, c, p2, far), anchor) <= retreat:
            return far  # the whole piece lies within the head
        # near is within the retreat, far beyond it: bisect toward the boundary
        for _ in range(48):
            mid = (near + far) / 2.0
            if _distance(_quad_at(p0, c, p2, mid), anchor) > retreat:
                far = mid
            else:
                near = mid
        return (near + far) / 2.0

    def _arrowhead_polygon(self) -> QPolygonF:
        """The head's outline as a polygon (kept for callers that had the one filled head)."""
        filled, _lines, _shaft = self.head_paths()
        return filled.toFillPolygon()

    def line_path(self) -> QPainterPath:
        """The whole centre line from the tail to the head, in its line style."""
        path = QPainterPath()
        path.moveTo(self._line.p1())
        if self._line_style is LineStyle.CURVED:
            path.quadTo(self.effective_control_point(), self._line.p2())
        elif self._line_style is LineStyle.ELBOW:
            for point in self.elbow_points()[1:]:
                path.lineTo(point)
        else:
            path.lineTo(self._line.p2())
        return path

    def boundingRect(self) -> QRectF:
        margin = self.effective_head_size() + self._stroke_width + 4
        body = (
            self.line_path()
            .boundingRect()
            .united(QRectF(self._line.p1(), self._line.p2()).normalized())
            .adjusted(-margin, -margin, margin, margin)
        )
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return (
            self.line_path()
            .boundingRect()
            .united(QRectF(self._line.p1(), self._line.p2()).normalized())
        )

    def shape(self) -> QPainterPath:
        filled, lines, _shaft = self.head_paths()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._stroke_width, 4.0))
        stroke_path = stroker.createStroke(self.line_path())
        stroke_path.addPath(filled)
        if not lines.isEmpty():
            stroke_path.addPath(stroker.createStroke(lines))
        return stroke_path

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        filled, lines, shaft = self.head_paths()
        shadow = self.shadow_path(shaft, closed=False)
        if not filled.isEmpty():
            shadow = shadow.united(filled.united(self.stroke_outline(filled)))
        if not lines.isEmpty():
            shadow = shadow.united(self.stroke_outline(lines))
        self.paint_shadow(painter, shadow)
        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if shaft.length() > 0.0:
            painter.drawPath(shaft)
        if not lines.isEmpty():
            # The open head keeps a round cap (4.4) and a solid line
            open_pen = QPen(pen)
            open_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            open_pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(open_pen)
            painter.drawPath(lines)
        if not filled.isEmpty():
            # The filled heads take the stroke colour at the stroke opacity (4.4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(with_alpha(self._stroke_color, self._stroke_opacity)))
            painter.drawPath(filled)
        self._end_flip(painter)

    # ------------------------------------------------------------ creation defaults

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        head = defaults.get("head_style")
        if isinstance(head, HeadStyle):
            self._head_style = head
        tail = defaults.get("tail_style")
        if isinstance(tail, HeadStyle):
            self._tail_style = tail
        size = defaults.get("head_size")
        if isinstance(size, HeadSize):
            self._head_size = size
        if "head_size_custom" in defaults:
            self.head_size_custom = float(defaults["head_size_custom"])
        style = defaults.get("line_style")
        if isinstance(style, LineStyle):
            self._line_style = style
        self._geometry_changed()

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "ArrowItem"
        data["line"] = [
            self._line.x1(),
            self._line.y1(),
            self._line.x2(),
            self._line.y2(),
        ]
        data["head_style"] = self._head_style.value
        data["tail_style"] = self._tail_style.value
        data["head_size"] = self._head_size.value
        data["head_size_custom"] = self._head_size_custom
        data["line_style"] = self._line_style.value
        data["control_point"] = point_to_data(self._control_point)
        data["bend_point"] = point_to_data(self._bend_point)
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> ArrowItem:
        coords = data.get("line", [0, 0, 100, 0])
        item = cls(line=QLineF(QPointF(coords[0], coords[1]), QPointF(coords[2], coords[3])))
        item._apply_base_data(data)
        # A file saved before the arrowheads existed drew one filled head (decision 3).
        item._head_style = _enum(HeadStyle, data.get("head_style"), HeadStyle.FILLED)
        item._tail_style = _enum(HeadStyle, data.get("tail_style"), HeadStyle.NONE)
        item._head_size = _enum(HeadSize, data.get("head_size"), HeadSize.MEDIUM)
        item.head_size_custom = float(data.get("head_size_custom", 0.0))
        item._line_style = _enum(LineStyle, data.get("line_style"), LineStyle.STRAIGHT)
        item._control_point = point_from_data(data.get("control_point"))
        item._bend_point = point_from_data(data.get("bend_point"))
        return item


def quad_shaft(
    p0: QPointF, c: QPointF, p2: QPointF, tail_retreat: float, head_retreat: float
) -> QPainterPath:
    """The quadratic from *p0* through *c* to *p2* with *tail_retreat* taken off the start
    and *head_retreat* off the end, each measured straight from the end point, so a shaft
    stops at a filled head's base (4.4, 4.5); shared by the arrow and the arc (7.3)."""
    path = QPainterPath()
    b = ArrowItem._curve_parameter(p0, c, p2, p2, head_retreat, 0.0, 1.0, from_end=True)
    a = ArrowItem._curve_parameter(p0, c, p2, p0, tail_retreat, 0.0, b, from_end=False)
    if b - a <= _EPSILON:
        return path
    path.moveTo(_quad_at(p0, c, p2, a))
    path.quadTo(_quad_blossom(p0, c, p2, a, b), _quad_at(p0, c, p2, b))
    return path
