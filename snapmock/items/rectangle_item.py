"""RectangleItem — rectangle / square annotation with optional corner radius.

Basic Shape PRD Section 5: ``corner_radius`` rounds all four corners in Uniform mode;
Individual mode (``corner_radius_mode``) rounds each corner by its own radius, the path
built with one ``arcTo`` per corner (5.5). Every radius is stored as set and drawn clamped
to half the smaller side, so a later resize restores the rounding the user chose.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainter, QPainterPath

from snapmock.config.constants import CORNER_KEYS, CORNER_RADIUS_MAX, CornerRadiusMode
from snapmock.items.vector_item import VectorItem, _enum


def _clamp_radius(value: object) -> float:
    try:
        return max(0.0, min(CORNER_RADIUS_MAX, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


class RectangleItem(VectorItem):
    """A rectangle (optionally rounded) annotation item."""

    def __init__(
        self,
        rect: QRectF | None = None,
        corner_radius: float = 0.0,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._rect: QRectF = rect if rect is not None else QRectF(0, 0, 100, 60)
        self._corner_radius: float = corner_radius
        self._corner_radius_mode: CornerRadiusMode = CornerRadiusMode.UNIFORM
        self._corners: dict[str, float] = dict.fromkeys(CORNER_KEYS, 0.0)

    @property
    def rect(self) -> QRectF:
        return QRectF(self._rect)

    @rect.setter
    def rect(self, value: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(value)
        self.update()

    @property
    def corner_radius(self) -> float:
        return self._corner_radius

    @corner_radius.setter
    def corner_radius(self, value: float) -> None:
        """Stored as given (0 to 200); drawn clamped to half the smaller side (Basic Shape
        PRD 5.3), so a later resize restores the rounding the user set."""
        self._corner_radius = _clamp_radius(value)
        self._geometry_changed()

    @property
    def corner_radius_mode(self) -> CornerRadiusMode:
        """Uniform (``corner_radius`` for every corner) or Individual (5.3)."""
        return self._corner_radius_mode

    @corner_radius_mode.setter
    def corner_radius_mode(self, value: CornerRadiusMode) -> None:
        mode = CornerRadiusMode(value)
        if (
            mode is CornerRadiusMode.INDIVIDUAL
            and self._corner_radius_mode is CornerRadiusMode.UNIFORM
            and not any(self._corners.values())
        ):
            # Switching a rounded rectangle to Individual keeps its look
            self._corners = dict.fromkeys(CORNER_KEYS, self._corner_radius)
        self._corner_radius_mode = mode
        self._geometry_changed()

    def _set_corner(self, key: str, value: float) -> None:
        self._corners[key] = _clamp_radius(value)
        self._geometry_changed()

    @property
    def corner_radius_tl(self) -> float:
        return self._corners["corner_radius_tl"]

    @corner_radius_tl.setter
    def corner_radius_tl(self, value: float) -> None:
        self._set_corner("corner_radius_tl", value)

    @property
    def corner_radius_tr(self) -> float:
        return self._corners["corner_radius_tr"]

    @corner_radius_tr.setter
    def corner_radius_tr(self, value: float) -> None:
        self._set_corner("corner_radius_tr", value)

    @property
    def corner_radius_bl(self) -> float:
        return self._corners["corner_radius_bl"]

    @corner_radius_bl.setter
    def corner_radius_bl(self, value: float) -> None:
        self._set_corner("corner_radius_bl", value)

    @property
    def corner_radius_br(self) -> float:
        return self._corners["corner_radius_br"]

    @corner_radius_br.setter
    def corner_radius_br(self, value: float) -> None:
        self._set_corner("corner_radius_br", value)

    def _limit(self) -> float:
        return max(0.0, min(self._rect.width(), self._rect.height()) / 2.0)

    def effective_corner_radius(self) -> float:
        """The uniform radius drawn: ``corner_radius`` clamped to half the smaller side."""
        return max(0.0, min(self._corner_radius, self._limit()))

    def effective_corner_radii(self) -> tuple[float, float, float, float]:
        """The four radii drawn (top-left, top-right, bottom-left, bottom-right), each
        clamped to half the smaller side, so two adjacent corners never overlap."""
        if self._corner_radius_mode is CornerRadiusMode.UNIFORM:
            r = self.effective_corner_radius()
            return (r, r, r, r)
        limit = self._limit()
        tl, tr, bl, br = (min(self._corners[k], limit) for k in CORNER_KEYS)
        return (tl, tr, bl, br)

    def outline(self) -> QPainterPath:
        """The rectangle's edge: rounded uniformly, or corner by corner in Individual mode
        with one ``arcTo`` per corner (5.5)."""
        path = QPainterPath()
        if self._corner_radius_mode is CornerRadiusMode.UNIFORM:
            radius = self.effective_corner_radius()
            if radius > 0:
                path.addRoundedRect(self._rect, radius, radius)
            else:
                path.addRect(self._rect)
            return path
        tl, tr, bl, br = self.effective_corner_radii()
        if not (tl or tr or bl or br):
            path.addRect(self._rect)
            return path
        r = self._rect
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        path.moveTo(QPointF(x + tl, y))
        path.lineTo(QPointF(x + w - tr, y))
        if tr > 0:
            path.arcTo(QRectF(x + w - 2 * tr, y, 2 * tr, 2 * tr), 90.0, -90.0)
        path.lineTo(QPointF(x + w, y + h - br))
        if br > 0:
            path.arcTo(QRectF(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br), 0.0, -90.0)
        path.lineTo(QPointF(x + bl, y + h))
        if bl > 0:
            path.arcTo(QRectF(x, y + h - 2 * bl, 2 * bl, 2 * bl), 270.0, -90.0)
        path.lineTo(QPointF(x, y + tl))
        if tl > 0:
            path.arcTo(QRectF(x, y, 2 * tl, 2 * tl), 180.0, -90.0)
        path.closeSubpath()
        return path

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        if "corner_radius" in defaults:
            self.corner_radius = float(defaults["corner_radius"])
        for key in CORNER_KEYS:
            if key in defaults:
                self._corners[key] = _clamp_radius(defaults[key])
        mode = defaults.get("corner_radius_mode")
        if isinstance(mode, CornerRadiusMode):
            self._corner_radius_mode = mode
        self._geometry_changed()

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        self._rect = QRectF(
            self._rect.x() * sx,
            self._rect.y() * sy,
            self._rect.width() * sx,
            self._rect.height() * sy,
        )
        factor = (sx + sy) / 2.0
        self._corner_radius *= factor
        self._corners = {k: v * factor for k, v in self._corners.items()}

    # --- QGraphicsItem overrides ---

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
        outline = self.outline()
        self.paint_shadow(painter, self.shadow_path(outline))
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        if self._corner_radius_mode is CornerRadiusMode.INDIVIDUAL:
            painter.drawPath(outline)
        else:
            radius = self.effective_corner_radius()
            if radius > 0:
                painter.drawRoundedRect(self._rect, radius, radius)
            else:
                painter.drawRect(self._rect)
        self._end_flip(painter)

    # --- serialization ---

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "RectangleItem"
        data["rect"] = [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()]
        data["corner_radius"] = self._corner_radius
        data["corner_radius_mode"] = self._corner_radius_mode.value
        for key in CORNER_KEYS:
            data[key] = self._corners[key]
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> RectangleItem:
        r = data.get("rect", [0, 0, 100, 60])
        item = cls(rect=QRectF(r[0], r[1], r[2], r[3]), corner_radius=data.get("corner_radius", 0))
        item._apply_base_data(data)
        # Absent in files saved before the individual radii (10.3): Uniform, all zero
        item._corner_radius_mode = _enum(
            CornerRadiusMode, data.get("corner_radius_mode"), CornerRadiusMode.UNIFORM
        )
        for key in CORNER_KEYS:
            item._corners[key] = _clamp_radius(data.get(key, 0.0))
        return item
