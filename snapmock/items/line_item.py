"""LineItem — straight line annotation."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QPainterPathStroker

from snapmock.items.vector_item import VectorItem


class LineItem(VectorItem):
    """A straight-line annotation item."""

    def __init__(
        self,
        line: QLineF | None = None,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._line: QLineF = line if line is not None else QLineF(0, 0, 100, 0)

    @property
    def line(self) -> QLineF:
        return QLineF(self._line)

    @line.setter
    def line(self, value: QLineF) -> None:
        self.prepareGeometryChange()
        self._line = QLineF(value)
        self.update()

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._line = QLineF(
            self._line.x1() * sx,
            self._line.y1() * sy,
            self._line.x2() * sx,
            self._line.y2() * sy,
        )

    def line_path(self) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(self._line.p1())
        path.lineTo(self._line.p2())
        return path

    def boundingRect(self) -> QRectF:
        margin = self.stroke_margin() + 2.0
        body = (
            QRectF(self._line.p1(), self._line.p2())
            .normalized()
            .adjusted(-margin, -margin, margin, margin)
        )
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return QRectF(self._line.p1(), self._line.p2()).normalized()

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._stroke_width, 4.0))
        return stroker.createStroke(self.line_path())

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        self.paint_shadow(painter, self.shadow_path(self.line_path(), closed=False))
        painter.setPen(self.pen())
        painter.drawLine(self._line)
        self._end_flip(painter)

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "LineItem"
        data["line"] = [
            self._line.x1(),
            self._line.y1(),
            self._line.x2(),
            self._line.y2(),
        ]
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> LineItem:
        coords = data.get("line", [0, 0, 100, 0])
        item = cls(line=QLineF(QPointF(coords[0], coords[1]), QPointF(coords[2], coords[3])))
        item._apply_base_data(data)
        return item
