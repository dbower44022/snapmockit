"""TextItem — editable rich text annotation with optional frame.

Text & Callout Annotation Tools PRD Section 3. The item sits beside ``VectorItem`` rather
than under it (Vector Item Properties decision 1, option B) and carries the shadow helper
and the two opacities directly: the background is the fill for ``fill_opacity``, the
border the stroke for ``stroke_opacity``, and the shadow of 3.7 is drawn first under the
box shape with the Basic Shape PRD's defaults.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen

from snapmock.config.constants import (
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT_BG_COLOR,
    DEFAULT_TEXT_BORDER_COLOR,
    DEFAULT_TEXT_BORDER_RADIUS,
    DEFAULT_TEXT_BORDER_WIDTH,
    DEFAULT_TEXT_PADDING,
    DEFAULT_TEXT_WIDTH,
    DEFAULT_VECTOR_SHADOW_BLUR,
    DEFAULT_VECTOR_SHADOW_COLOR,
    DEFAULT_VECTOR_SHADOW_OFFSET,
    MIN_TEXT_BOX_HEIGHT,
    MIN_TEXT_BOX_WIDTH,
    BorderStyle,
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


class TextItem(ShadowMixin, RichTextMixin, SnapGraphicsItem):
    """An editable text annotation item backed by QTextDocument."""

    def __init__(
        self,
        text: str = "Text",
        pos_x: float = 0,
        pos_y: float = 0,
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
        font = QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE)
        color = QColor(Qt.GlobalColor.black)
        self._init_document(text, font, color)
        self._width: float = DEFAULT_TEXT_WIDTH
        self._height: float | None = None  # None = auto-size from document
        self._bg_color: QColor = QColor(DEFAULT_TEXT_BG_COLOR)
        self._border_color: QColor = QColor(DEFAULT_TEXT_BORDER_COLOR)
        self._border_width: float = DEFAULT_TEXT_BORDER_WIDTH
        self._border_radius: float = DEFAULT_TEXT_BORDER_RADIUS
        self._border_style: BorderStyle = BorderStyle.SOLID
        self._padding: float = DEFAULT_TEXT_PADDING
        self._vertical_align: VerticalAlign = VerticalAlign.TOP
        self._auto_size: bool = True
        self._auto_width: bool = True
        self._text_scale_factor: float = 1.0
        self._min_width: float = DEFAULT_TEXT_WIDTH
        self._min_height: float | None = None  # None = 1 line + padding
        self.setPos(pos_x, pos_y)

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
    def text_width(self) -> float:
        return self._width

    @text_width.setter
    def text_width(self, value: float) -> None:
        self.prepareGeometryChange()
        self._width = max(20.0, value)
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
        """Opacity of the background fill, 0.0 to 1.0 (Text PRD 7.2; General UI PRD 8.3)."""
        return self._fill_opacity

    @fill_opacity.setter
    def fill_opacity(self, value: float) -> None:
        self._fill_opacity = _clamp_unit(value)
        self.update()

    @property
    def stroke_opacity(self) -> float:
        """Opacity of the border, 0.0 to 1.0 (Text PRD 7.2; General UI PRD 8.3)."""
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
    def auto_size(self) -> bool:
        return self._auto_size

    @auto_size.setter
    def auto_size(self, value: bool) -> None:
        self.prepareGeometryChange()
        self._auto_size = value
        if value:
            self._height = None
        self.update()

    @property
    def text_height(self) -> float | None:
        return self._height

    @text_height.setter
    def text_height(self, value: float | None) -> None:
        self.prepareGeometryChange()
        self._height = value
        self.update()

    @property
    def auto_width(self) -> bool:
        return self._auto_width

    @auto_width.setter
    def auto_width(self, value: bool) -> None:
        self.prepareGeometryChange()
        self._auto_width = value
        self.update()

    @property
    def text_scale_factor(self) -> float:
        return self._text_scale_factor

    @text_scale_factor.setter
    def text_scale_factor(self, value: float) -> None:
        self.prepareGeometryChange()
        self._text_scale_factor = max(0.01, value)
        self.update()

    @property
    def min_width(self) -> float:
        return self._min_width

    @min_width.setter
    def min_width(self, value: float) -> None:
        self.prepareGeometryChange()
        self._min_width = max(MIN_TEXT_BOX_WIDTH, value)
        self.update()

    @property
    def min_height(self) -> float | None:
        return self._min_height

    @min_height.setter
    def min_height(self, value: float | None) -> None:
        self.prepareGeometryChange()
        self._min_height = value
        self.update()

    # --- geometry helpers ---

    def _content_width(self) -> float:
        w = self._item_width() if self._auto_width else self._width
        return max(1.0, w - 2 * self._padding)

    def _effective_width(self) -> float:
        """Return the actual item width, respecting auto_width and min_width."""
        if self._auto_width:
            # Let document determine ideal width (no wrapping)
            self._document.setTextWidth(-1)
            ideal = self._document.idealWidth() + 2 * self._padding
            effective_min = max(self._min_width, MIN_TEXT_BOX_WIDTH)
            return max(ideal, effective_min)
        return max(self._width, self._min_width, MIN_TEXT_BOX_WIDTH)

    def _frame_height(self) -> float:
        if self._auto_size or self._height is None:
            content_w = self._content_width()
            h = self.document_height(content_w) + 2 * self._padding
            # Respect min_height
            if self._min_height is not None:
                h = max(h, self._min_height)
            return max(h, MIN_TEXT_BOX_HEIGHT)
        h = self._height
        if self._min_height is not None:
            h = max(h, self._min_height)
        return max(h, MIN_TEXT_BOX_HEIGHT)

    def scale_geometry(self, sx: float, sy: float) -> None:
        self.prepareGeometryChange()
        self._shadow_cache_key = None
        avg = (sx + sy) / 2.0
        self._width = max(MIN_TEXT_BOX_WIDTH, self._width * sx)
        if self._height is not None:
            self._height = max(1.0, self._height * sy)
        self._min_width = max(MIN_TEXT_BOX_WIDTH, self._min_width * sx)
        if self._min_height is not None:
            self._min_height = max(MIN_TEXT_BOX_HEIGHT, self._min_height * sy)
        self._padding = max(0.0, self._padding * avg)
        self._border_width = max(0.0, self._border_width * avg)
        self._border_radius = max(0.0, self._border_radius * avg)

    def _item_width(self) -> float:
        """Return the effective width for rendering."""
        if self._auto_width:
            return self._effective_width()
        return max(self._width, self._min_width, MIN_TEXT_BOX_WIDTH)

    def frame_path(self) -> QPainterPath:
        """The box shape of Text PRD 3.7 step 1: the frame, rounded by ``border_radius``."""
        frame = QRectF(0, 0, self._item_width(), self._frame_height())
        path = QPainterPath()
        if self._border_radius > 0:
            path.addRoundedRect(frame, self._border_radius, self._border_radius)
        else:
            path.addRect(frame)
        return path

    def shadow_path(self) -> QPainterPath:
        """What the shadow duplicates: the box shape, plus the border's area when the
        border is drawn (the frame is the PRD's shape whether or not it is painted)."""
        path = self.frame_path()
        if self._border_width > 0 and self._border_color.alpha() > 0:
            stroker = QPainterPathStroker()
            stroker.setWidth(self._border_width)
            path = path.united(stroker.createStroke(path))
        return path

    def boundingRect(self) -> QRectF:
        w = self._item_width()
        frame = QRectF(0, 0, w, self._frame_height())
        half = self._border_width / 2
        body = frame.adjusted(-half, -half, half, half)
        return body.united(self.shadow_rect(body))

    def geometry_rect(self) -> QRectF:
        return QRectF(0, 0, self._item_width(), self._frame_height())

    def shape(self) -> QPainterPath:
        """Return the clickable shape for hit testing.

        If the background or border is visible the full frame rect is
        clickable.  Otherwise only the text-content bounding box is
        returned so invisible text boxes don't steal clicks from items
        behind them.
        """
        path = QPainterPath()
        has_bg = self._bg_color.alpha() > 0
        has_border = self._border_width > 0 and self._border_color.alpha() > 0
        if has_bg or has_border:
            w = self._item_width()
            frame = QRectF(0, 0, w, self._frame_height())
            if self._border_radius > 0:
                path.addRoundedRect(frame, self._border_radius, self._border_radius)
            else:
                path.addRect(frame)
        else:
            # Only the text content area is clickable.
            # Must incorporate vertical alignment offset per PRD Section 3.8.
            w = self._item_width()
            content_w = max(1.0, w - 2 * self._padding)
            doc_h = self.document_height(content_w)
            frame_h = self._frame_height()
            inner_h = frame_h - 2 * self._padding
            y_offset = self._padding
            if self._vertical_align == VerticalAlign.CENTER:
                y_offset += max(0.0, (inner_h - doc_h) / 2)
            elif self._vertical_align == VerticalAlign.BOTTOM:
                y_offset += max(0.0, inner_h - doc_h)
            text_rect = QRectF(self._padding, y_offset, content_w, doc_h)
            path.addRect(text_rect)
        return path

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)

        w = self._item_width()
        frame_rect = QRectF(0, 0, w, self._frame_height())

        # The shadow first (Text PRD 3.7 step 2)
        self.paint_shadow(painter, self.shadow_path())

        # Draw background fill (if alpha > 0)
        if self._bg_color.alpha() > 0:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(with_alpha(self._bg_color, self._fill_opacity)))
            if self._border_radius > 0:
                painter.drawRoundedRect(frame_rect, self._border_radius, self._border_radius)
            else:
                painter.drawRect(frame_rect)
            painter.restore()

        # Draw border (if width > 0 and alpha > 0)
        if self._border_width > 0 and self._border_color.alpha() > 0:
            painter.save()
            pen = QPen(with_alpha(self._border_color, self._stroke_opacity), self._border_width)
            pen.setStyle(STROKE_STYLE_MAP.get(self._border_style, Qt.PenStyle.SolidLine))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self._border_radius > 0:
                painter.drawRoundedRect(frame_rect, self._border_radius, self._border_radius)
            else:
                painter.drawRect(frame_rect)
            painter.restore()

        # Draw edit-mode indicator
        if self._is_editing:
            painter.save()
            pen = QPen(QColor("#0078d7"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(frame_rect)
            painter.restore()

        # Compute text rect with padding and vertical alignment
        content_w = max(1.0, w - 2 * self._padding)
        doc_h = self.document_height(content_w)
        frame_h = frame_rect.height()
        inner_h = frame_h - 2 * self._padding

        y_offset = self._padding
        if self._vertical_align == VerticalAlign.CENTER:
            y_offset += max(0.0, (inner_h - doc_h) / 2)
        elif self._vertical_align == VerticalAlign.BOTTOM:
            y_offset += max(0.0, inner_h - doc_h)

        text_rect = QRectF(self._padding, y_offset, content_w, doc_h)

        # Apply text_scale_factor if set
        if self._text_scale_factor != 1.0:
            painter.save()
            painter.translate(text_rect.topLeft())
            painter.scale(self._text_scale_factor, self._text_scale_factor)
            scaled_rect = QRectF(
                0,
                0,
                content_w / self._text_scale_factor,
                doc_h / self._text_scale_factor,
            )
            self.draw_document(painter, scaled_rect)
            painter.restore()
        else:
            self.draw_document(painter, text_rect)
        self._end_flip(painter)

    def serialize(self) -> dict[str, Any]:
        font = self._document.defaultFont()
        return {
            "type": "TextItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "transform": self._transform_entry(),
            "text": self._document.toPlainText(),
            "html": self._document.toHtml(),
            "font_family": font.family(),
            "font_size": font.pointSize(),
            "color": self._get_text_color().name(QColor.NameFormat.HexArgb),
            "width": self._width,
            "height": self._height,
            "bg_color": self._bg_color.name(QColor.NameFormat.HexArgb),
            "border_color": self._border_color.name(QColor.NameFormat.HexArgb),
            "border_width": self._border_width,
            "border_radius": self._border_radius,
            "border_style": self._border_style.value,
            "padding": self._padding,
            "vertical_align": self._vertical_align.value,
            "auto_size": self._auto_size,
            "auto_width": self._auto_width,
            "text_scale_factor": self._text_scale_factor,
            "min_width": self._min_width,
            "min_height": self._min_height,
            "fill_opacity": self._fill_opacity,
            "stroke_opacity": self._stroke_opacity,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
            **self._shadow_data(),
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> TextItem:
        item = cls(text=data.get("text", "Text"))
        pos = data.get("pos", [0, 0])
        item.setPos(pos[0], pos[1])
        item._apply_transform_entry(data)
        item.item_id = data.get("item_id", item.item_id)
        item.layer_id = data.get("layer_id", "")
        item._width = data.get("width", DEFAULT_TEXT_WIDTH)

        # Frame properties (backward-compat defaults: transparent/zero)
        item._height = data.get("height", None)
        item._bg_color = QColor(data.get("bg_color", DEFAULT_TEXT_BG_COLOR))
        item._border_color = QColor(data.get("border_color", DEFAULT_TEXT_BORDER_COLOR))
        item._border_width = data.get("border_width", DEFAULT_TEXT_BORDER_WIDTH)
        item._border_radius = data.get("border_radius", DEFAULT_TEXT_BORDER_RADIUS)
        bs_str = data.get("border_style", BorderStyle.SOLID.value)
        try:
            item._border_style = BorderStyle(bs_str)
        except ValueError:
            item._border_style = BorderStyle.SOLID
        item._padding = data.get("padding", DEFAULT_TEXT_PADDING)
        va_str = data.get("vertical_align", VerticalAlign.TOP.value)
        try:
            item._vertical_align = VerticalAlign(va_str)
        except ValueError:
            item._vertical_align = VerticalAlign.TOP
        item._auto_size = data.get("auto_size", True)
        item._auto_width = data.get("auto_width", True)
        item._text_scale_factor = data.get("text_scale_factor", 1.0)
        item._min_width = data.get("min_width", DEFAULT_TEXT_WIDTH)
        item._min_height = data.get("min_height", None)
        item._flip_horizontal = data.get("flip_horizontal", False)
        item._flip_vertical = data.get("flip_vertical", False)
        item._apply_blend_entry(data)
        item._fill_opacity = _clamp_unit(data.get("fill_opacity", 1.0))
        item._stroke_opacity = _clamp_unit(data.get("stroke_opacity", 1.0))
        item._apply_shadow_data(data)

        if "html" in data:
            # Rich text: restore from HTML
            item._document.setHtml(data["html"])
            # Restore default font from serialized values for consistency
            font = QFont(
                data.get("font_family", DEFAULT_FONT_FAMILY),
                data.get("font_size", DEFAULT_FONT_SIZE),
            )
            item._document.setDefaultFont(font)
        else:
            # Legacy plain-text format
            font = QFont(
                data.get("font_family", DEFAULT_FONT_FAMILY),
                data.get("font_size", DEFAULT_FONT_SIZE),
            )
            color = QColor(data.get("color", "#ff000000"))
            item._init_document(data.get("text", "Text"), font, color)

        return item
