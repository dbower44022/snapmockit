"""CalloutItem — speech-bubble annotation with configurable shape and tail.

Text & Callout Annotation Tools PRD Section 4. The item sits beside ``VectorItem`` rather
than under it (Vector Item Properties decision 1, option B) and carries the shadow helper
and the two opacities directly: the background is the fill for ``fill_opacity``, the
border the stroke for ``stroke_opacity``, and the shadow of 4.8 is drawn first under the
combined bubble and tail shape with the Basic Shape PRD's defaults.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen

from snapmock.config.constants import (
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_VECTOR_SHADOW_BLUR,
    DEFAULT_VECTOR_SHADOW_COLOR,
    DEFAULT_VECTOR_SHADOW_OFFSET,
    BorderStyle,
    BubbleShape,
    TailBaseEdge,
    TailStyle,
    VerticalAlign,
)
from snapmock.core.rich_text_mixin import RichTextMixin
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.shadow import ShadowMixin
from snapmock.items.vector_item import STROKE_STYLE_MAP, with_alpha


def _clamp_unit(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0


class CalloutItem(ShadowMixin, RichTextMixin, SnapGraphicsItem):
    """A text callout with a pointer tail, backed by QTextDocument."""

    def __init__(
        self,
        text: str = "Callout",
        rect: QRectF | None = None,
        tail_tip: QPointF | None = None,
        parent: SnapGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_shadow(
            enabled=False,
            color=DEFAULT_VECTOR_SHADOW_COLOR,
            offset=DEFAULT_VECTOR_SHADOW_OFFSET,
            blur=DEFAULT_VECTOR_SHADOW_BLUR,
        )
        self._fill_opacity: float = 1.0
        self._stroke_opacity: float = 1.0
        self._rect = rect if rect is not None else QRectF(0, 0, 200, 80)
        self._tail_tip = tail_tip if tail_tip is not None else QPointF(100, 160)
        self._bg_color = QColor("#FFFFCC")
        self._border_color = QColor("#333333")
        self._border_width: float = 2.0
        self._border_radius: float = 12.0
        self._border_style: BorderStyle = BorderStyle.SOLID
        self._padding: float = 10.0
        self._vertical_align: VerticalAlign = VerticalAlign.TOP
        self._auto_height: bool = True

        # Bubble shape
        self._bubble_shape: BubbleShape = BubbleShape.ROUNDED_RECT
        self._starburst_points: int = 12

        # Tail properties
        self._tail_style: TailStyle = TailStyle.STRAIGHT
        self._tail_width: float = 20.0
        self._tail_base_position: float = 0.5
        self._tail_base_edge: TailBaseEdge = TailBaseEdge.AUTO
        self._tail_control_point: QPointF | None = None

        font = QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE)
        color = QColor(Qt.GlobalColor.black)
        self._init_document(text, font, color)

    # --- backward-compat property shims ---

    @property
    def text(self) -> str:
        return self._get_text()

    @text.setter
    def text(self, value: str) -> None:
        self._set_text(value)
        self.update()

    @property
    def font(self) -> QFont:
        return self._get_font()

    @font.setter
    def font(self, value: QFont) -> None:
        self.prepareGeometryChange()
        self._set_font(value)
        self.update()

    @property
    def horizontal_alignment(self) -> Qt.AlignmentFlag:
        """The first paragraph's horizontal alignment (Property Panel Align)."""
        return self.get_block_format().alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask

    @horizontal_alignment.setter
    def horizontal_alignment(self, value: Qt.AlignmentFlag) -> None:
        self.set_alignment(value)
        self.update()

    @property
    def text_color(self) -> QColor:
        return self._get_text_color()

    @text_color.setter
    def text_color(self, value: QColor) -> None:
        self._set_text_color(value)
        self.update()

    @property
    def line_spacing(self) -> float:
        """Line spacing as a multiplier for every paragraph (Text PRD 2.2; General UI PRD
        8.4): the first paragraph's value when read; every paragraph's when set."""
        return self._get_line_spacing()

    @line_spacing.setter
    def line_spacing(self, value: float) -> None:
        self.prepareGeometryChange()
        self._set_line_spacing(value)
        self.update()

    @property
    def line_spacings(self) -> list[float]:
        """Every paragraph's line spacing, the form the Property Panel's command carries so
        an undo restores paragraphs that differed."""
        return self.paragraph_line_spacings()

    @line_spacings.setter
    def line_spacings(self, values: list[float]) -> None:
        self.prepareGeometryChange()
        self._set_line_spacings(list(values))
        self.update()

    @property
    def tail_tip(self) -> QPointF:
        return QPointF(self._tail_tip)

    @tail_tip.setter
    def tail_tip(self, value: QPointF) -> None:
        self.prepareGeometryChange()
        self._tail_tip = QPointF(value)
        self.update()

    @property
    def box_rect(self) -> QRectF:
        return QRectF(self._rect)

    @box_rect.setter
    def box_rect(self, value: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(value)
        self.update()

    # --- frame properties ---

    @property
    def bg_color(self) -> QColor:
        return QColor(self._bg_color)

    @bg_color.setter
    def bg_color(self, value: QColor) -> None:
        self._bg_color = QColor(value)
        self.update()

    @property
    def border_color(self) -> QColor:
        return QColor(self._border_color)

    @border_color.setter
    def border_color(self, value: QColor) -> None:
        self._border_color = QColor(value)
        self.update()

    @property
    def border_width(self) -> float:
        return self._border_width

    @border_width.setter
    def border_width(self, value: float) -> None:
        self.prepareGeometryChange()
        self._border_width = max(0.0, value)
        self.update()

    @property
    def border_radius(self) -> float:
        return self._border_radius

    @border_radius.setter
    def border_radius(self, value: float) -> None:
        self._border_radius = max(0.0, value)
        self.update()

    @property
    def border_style(self) -> BorderStyle:
        return self._border_style

    @border_style.setter
    def border_style(self, value: BorderStyle) -> None:
        self._border_style = value
        self.update()

    @property
    def fill_opacity(self) -> float:
        """Opacity of the bubble fill, 0.0 to 1.0 (General UI PRD 8.3)."""
        return self._fill_opacity

    @fill_opacity.setter
    def fill_opacity(self, value: float) -> None:
        self._fill_opacity = _clamp_unit(value)
        self.update()

    @property
    def stroke_opacity(self) -> float:
        """Opacity of the bubble border, 0.0 to 1.0 (General UI PRD 8.3)."""
        return self._stroke_opacity

    @stroke_opacity.setter
    def stroke_opacity(self, value: float) -> None:
        self._stroke_opacity = _clamp_unit(value)
        self.update()

    @property
    def padding(self) -> float:
        return self._padding

    @padding.setter
    def padding(self, value: float) -> None:
        self.prepareGeometryChange()
        self._padding = max(0.0, value)
        self.update()

    @property
    def vertical_align(self) -> VerticalAlign:
        return self._vertical_align

    @vertical_align.setter
    def vertical_align(self, value: VerticalAlign) -> None:
        self._vertical_align = value
        self.update()

    @property
    def auto_height(self) -> bool:
        return self._auto_height

    @auto_height.setter
    def auto_height(self, value: bool) -> None:
        self.prepareGeometryChange()
        self._auto_height = value
        self.update()

    # --- bubble shape properties ---

    @property
    def bubble_shape(self) -> BubbleShape:
        return self._bubble_shape

    @bubble_shape.setter
    def bubble_shape(self, value: BubbleShape) -> None:
        self.prepareGeometryChange()
        self._bubble_shape = value
        self.update()

    @property
    def starburst_points(self) -> int:
        return self._starburst_points

    @starburst_points.setter
    def starburst_points(self, value: int) -> None:
        self._starburst_points = max(8, min(24, value))
        self.update()

    # --- tail properties ---

    @property
    def tail_style(self) -> TailStyle:
        return self._tail_style

    @tail_style.setter
    def tail_style(self, value: TailStyle) -> None:
        self.prepareGeometryChange()
        self._tail_style = value
        self.update()

    @property
    def tail_width(self) -> float:
        return self._tail_width

    @tail_width.setter
    def tail_width(self, value: float) -> None:
        self.prepareGeometryChange()
        self._tail_width = max(4.0, min(100.0, value))
        self.update()

    @property
    def tail_base_position(self) -> float:
        return self._tail_base_position

    @tail_base_position.setter
    def tail_base_position(self, value: float) -> None:
        self.prepareGeometryChange()
        self._tail_base_position = max(0.0, min(1.0, value))
        self.update()

    @property
    def tail_base_edge(self) -> TailBaseEdge:
        return self._tail_base_edge

    @tail_base_edge.setter
    def tail_base_edge(self, value: TailBaseEdge) -> None:
        self.prepareGeometryChange()
        self._tail_base_edge = value
        self.update()

    @property
    def tail_control_point(self) -> QPointF | None:
        return QPointF(self._tail_control_point) if self._tail_control_point else None

    @tail_control_point.setter
    def tail_control_point(self, value: QPointF | None) -> None:
        self.prepareGeometryChange()
        self._tail_control_point = QPointF(value) if value else None
        self.update()

    # --- geometry ---

    def _effective_rect(self) -> QRectF:
        """Return the bubble rect, auto-sizing height if needed."""
        if self._auto_height:
            p = self._padding
            content_w = max(1.0, self._rect.width() - 2 * p)
            doc_h = self.document_height(content_w)
            h = max(self._rect.height(), doc_h + 2 * p)
            return QRectF(self._rect.x(), self._rect.y(), self._rect.width(), h)
        return QRectF(self._rect)

    def _resolve_tail_edge(self) -> TailBaseEdge:
        """Determine which edge the tail attaches to."""
        if self._tail_base_edge != TailBaseEdge.AUTO:
            return self._tail_base_edge
        r = self._effective_rect()
        cx, cy = r.center().x(), r.center().y()
        tx, ty = self._tail_tip.x(), self._tail_tip.y()
        dx, dy = tx - cx, ty - cy
        if abs(dx) > abs(dy):
            return TailBaseEdge.RIGHT if dx > 0 else TailBaseEdge.LEFT
        return TailBaseEdge.BOTTOM if dy > 0 else TailBaseEdge.TOP

    def _tail_base_points(self) -> tuple[QPointF, QPointF, QPointF]:
        """Return (base_center, base_left, base_right) for the tail attachment."""
        r = self._effective_rect()
        edge = self._resolve_tail_edge()
        pos = self._tail_base_position
        hw = self._tail_width / 2

        if edge == TailBaseEdge.BOTTOM:
            bx = r.left() + pos * r.width()
            by = r.bottom()
            return QPointF(bx, by), QPointF(bx - hw, by), QPointF(bx + hw, by)
        elif edge == TailBaseEdge.TOP:
            bx = r.left() + pos * r.width()
            by = r.top()
            return QPointF(bx, by), QPointF(bx - hw, by), QPointF(bx + hw, by)
        elif edge == TailBaseEdge.RIGHT:
            bx = r.right()
            by = r.top() + pos * r.height()
            return QPointF(bx, by), QPointF(bx, by - hw), QPointF(bx, by + hw)
        else:  # LEFT
            bx = r.left()
            by = r.top() + pos * r.height()
            return QPointF(bx, by), QPointF(bx, by - hw), QPointF(bx, by + hw)

    def _bubble_path(self) -> QPainterPath:
        """Return the QPainterPath for the bubble shape only."""
        r = self._effective_rect()
        path = QPainterPath()
        shape = self._bubble_shape

        if shape == BubbleShape.RECT:
            path.addRect(r)
        elif shape == BubbleShape.ELLIPSE:
            path.addEllipse(r)
        elif shape == BubbleShape.PILL:
            radius = r.height() / 2
            path.addRoundedRect(r, radius, radius)
        elif shape == BubbleShape.CLOUD:
            path = self._cloud_path(r)
        elif shape == BubbleShape.STARBURST:
            path = self._starburst_path(r)
        else:  # ROUNDED_RECT (default)
            rad = self._border_radius
            path.addRoundedRect(r, rad, rad)

        return path

    def _cloud_path(self, r: QRectF) -> QPainterPath:
        """Generate a cloud-shaped outline from overlapping circles."""
        path = QPainterPath()
        cx, cy = r.center().x(), r.center().y()
        rx, ry = r.width() / 2 * 0.85, r.height() / 2 * 0.85
        n = 12
        circle_r = min(r.width(), r.height()) * 0.18
        for i in range(n):
            angle = 2 * math.pi * i / n
            px = cx + rx * math.cos(angle)
            py = cy + ry * math.sin(angle)
            path.addEllipse(QPointF(px, py), circle_r, circle_r)
        return path.simplified()

    def _starburst_path(self, r: QRectF) -> QPainterPath:
        """Generate a starburst shape with jagged edges."""
        path = QPainterPath()
        cx, cy = r.center().x(), r.center().y()
        outer_rx, outer_ry = r.width() / 2, r.height() / 2
        inner_rx, inner_ry = outer_rx * 0.7, outer_ry * 0.7
        n = self._starburst_points

        for i in range(n * 2):
            angle = math.pi * i / n - math.pi / 2
            if i % 2 == 0:
                px = cx + outer_rx * math.cos(angle)
                py = cy + outer_ry * math.sin(angle)
            else:
                px = cx + inner_rx * math.cos(angle)
                py = cy + inner_ry * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path

    def _tail_path(self) -> QPainterPath:
        """Return the QPainterPath for the tail only."""
        _, base_left, base_right = self._tail_base_points()
        tip = self._tail_tip
        path = QPainterPath()

        if self._tail_style == TailStyle.CURVED:
            ctrl = self._tail_control_point
            if ctrl is None:
                # Auto-calculate control point
                mid_x = (base_left.x() + base_right.x()) / 2
                mid_y = (base_left.y() + base_right.y()) / 2
                ctrl = QPointF(
                    (mid_x + tip.x()) / 2 + (tip.y() - mid_y) * 0.3,
                    (mid_y + tip.y()) / 2 - (tip.x() - mid_x) * 0.3,
                )
            path.moveTo(base_left)
            path.quadTo(ctrl, tip)
            path.quadTo(ctrl, base_right)
            path.closeSubpath()
        elif self._tail_style == TailStyle.ELBOW:
            ctrl = self._tail_control_point
            if ctrl is None:
                # Auto: extend perpendicular from base, then turn to tip
                edge = self._resolve_tail_edge()
                base_cx = (base_left.x() + base_right.x()) / 2
                base_cy = (base_left.y() + base_right.y()) / 2
                if edge in (TailBaseEdge.TOP, TailBaseEdge.BOTTOM):
                    ctrl = QPointF(base_cx, tip.y())
                else:
                    ctrl = QPointF(tip.x(), base_cy)
            path.moveTo(base_left)
            path.lineTo(ctrl)
            path.lineTo(tip)
            path.lineTo(ctrl)
            path.lineTo(base_right)
            path.closeSubpath()
        else:  # STRAIGHT
            path.moveTo(base_left)
            path.lineTo(tip)
            path.lineTo(base_right)
            path.closeSubpath()

        return path

    def _combined_path(self) -> QPainterPath:
        """Return a unified bubble+tail path for seamless rendering."""
        bubble = self._bubble_path()
        if self._bubble_shape == BubbleShape.CLOUD:
            # Cloud uses circle-chain tail, not connected path
            return bubble
        tail = self._tail_path()
        return bubble.united(tail)

    def shadow_path(self) -> QPainterPath:
        """What the shadow duplicates (Text PRD 4.8): the combined bubble and tail shape,
        the bubble and its tail circles for the cloud, plus the border's area."""
        path = QPainterPath(self._combined_path())
        if self._bubble_shape == BubbleShape.CLOUD:
            for center, radius in self._cloud_tail_circles():
                path.addEllipse(center, radius, radius)
        if self._border_width > 0 and self._border_color.alpha() > 0:
            stroker = QPainterPathStroker()
            stroker.setWidth(self._border_width)
            path = path.united(stroker.createStroke(path))
        return path

    def scale_geometry(self, sx: float, sy: float) -> None:
        self._shadow_cache_key = None
        self._rect = QRectF(
            self._rect.x() * sx,
            self._rect.y() * sy,
            self._rect.width() * sx,
            self._rect.height() * sy,
        )
        self._tail_tip = QPointF(self._tail_tip.x() * sx, self._tail_tip.y() * sy)
        if self._tail_control_point is not None:
            self._tail_control_point = QPointF(
                self._tail_control_point.x() * sx,
                self._tail_control_point.y() * sy,
            )
        avg = (sx + sy) / 2.0
        self._border_width = max(0.0, self._border_width * avg)
        self._border_radius = max(0.0, self._border_radius * avg)
        self._padding = max(0.0, self._padding * avg)
        self._tail_width = max(4.0, self._tail_width * avg)

    def geometry_rect(self) -> QRectF:
        return QRectF(self._effective_rect())

    def boundingRect(self) -> QRectF:
        # The tail's own rectangle, not a null rectangle at the tip (a null rectangle
        # drops out of a union, so the tail was outside the bounding rect before the
        # Vector Item Properties work).
        r = self._effective_rect()
        if self._bubble_shape == BubbleShape.CLOUD:
            r = r.adjusted(-20, -20, 20, 20)
            for center, radius in self._cloud_tail_circles():
                r = r.united(
                    QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
                )
        else:
            r = r.united(self._tail_path().boundingRect())
        half = self._border_width / 2
        margin = max(half, 1.0)
        body = r.adjusted(-margin, -margin, margin, margin)
        return body.united(self.shadow_rect(body))

    def shape(self) -> QPainterPath:
        path = self._combined_path()
        # Add cloud tail circles to hit area
        if self._bubble_shape == BubbleShape.CLOUD:
            for center, radius in self._cloud_tail_circles():
                path.addEllipse(center, radius, radius)
        # Add padding around tail for easier clicking
        stroker_path = QPainterPath()
        stroker_path.addPath(path)
        return stroker_path

    def _cloud_tail_circles(self) -> list[tuple[QPointF, float]]:
        """Return (center, radius) for each circle in the cloud tail chain."""
        r = self._effective_rect()
        tip = self._tail_tip
        cx, cy = r.center().x(), r.center().y()
        # Start from the nearest edge point
        edge = self._resolve_tail_edge()
        if edge == TailBaseEdge.BOTTOM:
            start = QPointF(cx, r.bottom())
        elif edge == TailBaseEdge.TOP:
            start = QPointF(cx, r.top())
        elif edge == TailBaseEdge.RIGHT:
            start = QPointF(r.right(), cy)
        else:
            start = QPointF(r.left(), cy)

        n = 4
        circles = []
        radius = self._tail_width / 2
        for i in range(n):
            t = (i + 1) / (n + 1)
            px = start.x() + t * (tip.x() - start.x())
            py = start.y() + t * (tip.y() - start.y())
            circles.append((QPointF(px, py), radius))
            radius *= 0.6
        return circles

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)

        # The shadow first, under the combined bubble and tail shape (Text PRD 4.8)
        self.paint_shadow(painter, self.shadow_path())

        pen = QPen(with_alpha(self._border_color, self._stroke_opacity), self._border_width)
        pen.setStyle(STROKE_STYLE_MAP.get(self._border_style, Qt.PenStyle.SolidLine))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        brush = QBrush(with_alpha(self._bg_color, self._fill_opacity))

        if self._bubble_shape == BubbleShape.CLOUD:
            # Cloud: draw bubble, then circle-chain tail
            # Draw tail circles first (behind bubble)
            for center, radius in self._cloud_tail_circles():
                painter.setPen(pen)
                painter.setBrush(brush)
                painter.drawEllipse(center, radius, radius)
            # Draw bubble
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawPath(self._bubble_path())
        else:
            # Unified path for seamless tail-bubble rendering
            combined = self._combined_path()
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawPath(combined)

        # Draw edit-mode border
        if self._is_editing:
            painter.save()
            edit_pen = QPen(QColor("#0078d7"), 2)
            edit_pen.setCosmetic(True)
            painter.setPen(edit_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._effective_rect())
            painter.restore()

        # Draw text via document with padding and vertical alignment
        er = self._effective_rect()
        p = self._padding
        content_w = max(1.0, er.width() - 2 * p)
        content_h = max(1.0, er.height() - 2 * p)
        doc_h = self.document_height(content_w)

        y_offset = er.y() + p
        if self._vertical_align == VerticalAlign.CENTER:
            y_offset += max(0.0, (content_h - doc_h) / 2)
        elif self._vertical_align == VerticalAlign.BOTTOM:
            y_offset += max(0.0, content_h - doc_h)

        text_rect = QRectF(er.x() + p, y_offset, content_w, doc_h)
        self.draw_document(painter, text_rect)
        self._end_flip(painter)

    def serialize(self) -> dict[str, Any]:
        font = self._document.defaultFont()
        data: dict[str, Any] = {
            "type": "CalloutItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "transform": self._transform_entry(),
            "text": self._document.toPlainText(),
            "html": self._document.toHtml(),
            "rect": [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()],
            "tail_tip": [self._tail_tip.x(), self._tail_tip.y()],
            "bg_color": self._bg_color.name(QColor.NameFormat.HexArgb),
            "border_color": self._border_color.name(QColor.NameFormat.HexArgb),
            "border_width": self._border_width,
            "border_radius": self._border_radius,
            "border_style": self._border_style.value,
            "padding": self._padding,
            "vertical_align": self._vertical_align.value,
            "auto_height": self._auto_height,
            "bubble_shape": self._bubble_shape.value,
            "starburst_points": self._starburst_points,
            "tail_style": self._tail_style.value,
            "tail_width": self._tail_width,
            "tail_base_position": self._tail_base_position,
            "tail_base_edge": self._tail_base_edge.value,
            "font_family": font.family(),
            "font_size": font.pointSize(),
            "text_color": self._get_text_color().name(QColor.NameFormat.HexArgb),
            "fill_opacity": self._fill_opacity,
            "stroke_opacity": self._stroke_opacity,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
            **self._shadow_data(),
        }
        if self._tail_control_point is not None:
            data["tail_control_point"] = [
                self._tail_control_point.x(),
                self._tail_control_point.y(),
            ]
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> CalloutItem:
        r = data.get("rect", [0, 0, 200, 80])
        t = data.get("tail_tip", [100, 160])
        item = cls(
            text=data.get("text", "Callout"),
            rect=QRectF(r[0], r[1], r[2], r[3]),
            tail_tip=QPointF(t[0], t[1]),
        )
        pos = data.get("pos", [0, 0])
        item.setPos(pos[0], pos[1])
        item._apply_transform_entry(data)
        item.item_id = data.get("item_id", item.item_id)
        item.layer_id = data.get("layer_id", "")
        if "bg_color" in data:
            item._bg_color = QColor(data["bg_color"])
        if "border_color" in data:
            item._border_color = QColor(data["border_color"])
        item._border_width = data.get("border_width", 2.0)
        item._border_radius = data.get("border_radius", 12.0)
        item._padding = data.get("padding", 10.0)
        item._auto_height = data.get("auto_height", True)

        # Border style
        bs_str = data.get("border_style", BorderStyle.SOLID.value)
        try:
            item._border_style = BorderStyle(bs_str)
        except ValueError:
            item._border_style = BorderStyle.SOLID

        # Vertical align
        va_str = data.get("vertical_align", VerticalAlign.TOP.value)
        try:
            item._vertical_align = VerticalAlign(va_str)
        except ValueError:
            item._vertical_align = VerticalAlign.TOP

        # Bubble shape
        shape_str = data.get("bubble_shape", BubbleShape.ROUNDED_RECT.value)
        try:
            item._bubble_shape = BubbleShape(shape_str)
        except ValueError:
            item._bubble_shape = BubbleShape.ROUNDED_RECT
        item._starburst_points = data.get("starburst_points", 12)

        # Tail properties
        ts_str = data.get("tail_style", TailStyle.STRAIGHT.value)
        try:
            item._tail_style = TailStyle(ts_str)
        except ValueError:
            item._tail_style = TailStyle.STRAIGHT
        item._tail_width = data.get("tail_width", 20.0)
        item._tail_base_position = data.get("tail_base_position", 0.5)
        tbe_str = data.get("tail_base_edge", TailBaseEdge.AUTO.value)
        try:
            item._tail_base_edge = TailBaseEdge(tbe_str)
        except ValueError:
            item._tail_base_edge = TailBaseEdge.AUTO
        tcp = data.get("tail_control_point")
        if tcp is not None:
            item._tail_control_point = QPointF(tcp[0], tcp[1])
        item._flip_horizontal = data.get("flip_horizontal", False)
        item._flip_vertical = data.get("flip_vertical", False)
        item._apply_blend_entry(data)
        item._fill_opacity = _clamp_unit(data.get("fill_opacity", 1.0))
        item._stroke_opacity = _clamp_unit(data.get("stroke_opacity", 1.0))
        item._apply_shadow_data(data)

        # Rich text
        if "html" in data:
            item._document.setHtml(data["html"])
            if "font_family" in data or "font_size" in data:
                font = QFont(
                    data.get("font_family", DEFAULT_FONT_FAMILY),
                    data.get("font_size", DEFAULT_FONT_SIZE),
                )
                item._document.setDefaultFont(font)
        else:
            # Legacy plain-text format
            if "font_family" in data or "font_size" in data:
                font = QFont(
                    data.get("font_family", DEFAULT_FONT_FAMILY),
                    data.get("font_size", DEFAULT_FONT_SIZE),
                )
                text_color = QColor(data.get("text_color", "#ff000000"))
                item._init_document(data.get("text", "Callout"), font, text_color)
            elif "text_color" in data:
                item._set_text_color(QColor(data["text_color"]))

        return item
