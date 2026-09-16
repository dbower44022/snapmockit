"""EllipseItem — ellipse / circle annotation."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QPainterPath

from snapmock.items.vector_item import VectorItem


class EllipseItem(VectorItem):
    """An ellipse annotation item."""

    def __init__(
        self,
        rect: QRectF | None = None,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._rect: QRectF = rect if rect is not None else QRectF(0, 0, 100, 100)

    @property
    def rect(self) -> QRectF:
        return QRectF(self._rect)

    @rect.setter
    def rect(self, value: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(value)
        self.update()

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._rect = QRectF(
            self._rect.x() * sx,
            self._rect.y() * sy,
            self._rect.width() * sx,
            self._rect.height() * sy,
        )

    def outline(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self._rect)
        return path

    def boundingRect(self) -> QRectF:
        margin = self.stroke_margin()
        body = self._rect.adjusted(-margin, -margin, margin, margin)
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return QRectF(self._rect)

    def shape(self) -> QPainterPath:
        return self.hit_shape(self.outline())

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        self.paint_shadow(painter, self.shadow_path(self.outline()))
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawEllipse(self._rect)
        self._end_flip(painter)

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "EllipseItem"
        data["rect"] = [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()]
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> EllipseItem:
        r = data.get("rect", [0, 0, 100, 100])
        item = cls(rect=QRectF(r[0], r[1], r[2], r[3]))
        item._apply_base_data(data)
        return item
