"""VectorItem — abstract base for items defined by vector paths.

Basic Shape Annotation Tools PRD Section 2.2 and Technical Architecture PRD Section 4.3:
every vector item shares the stroke colour, width, style, cap, and join, the fill colour,
the fill and stroke opacities, and the shadow (the helper of ``items/shadow.py``, mixed in
here with the Basic Shape PRD's defaults). The two opacities replace the base class's one
``opacity`` for vector items (Vector Item Properties decision 2): ``pen()`` and
``brush()`` carry them as alpha, and every subclass paints the shadow first through
:meth:`paint_shadow` over :meth:`shadow_path`.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen

from snapmock.config.constants import (
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    DEFAULT_VECTOR_SHADOW_BLUR,
    DEFAULT_VECTOR_SHADOW_COLOR,
    DEFAULT_VECTOR_SHADOW_OFFSET,
    BorderStyle,
    StrokeCap,
    StrokeJoin,
)
from snapmock.core.layer import normalize_item_blend_mode
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.shadow import ShadowMixin

STROKE_STYLE_MAP: dict[BorderStyle, Qt.PenStyle] = {
    BorderStyle.SOLID: Qt.PenStyle.SolidLine,
    BorderStyle.DASHED: Qt.PenStyle.DashLine,
    BorderStyle.DOTTED: Qt.PenStyle.DotLine,
    BorderStyle.DASHDOT: Qt.PenStyle.DashDotLine,
    BorderStyle.DASHDOTDOT: Qt.PenStyle.DashDotDotLine,
}
"""The Qt pen style for each stroke (or border) style."""

STROKE_CAP_MAP: dict[StrokeCap, Qt.PenCapStyle] = {
    StrokeCap.FLAT: Qt.PenCapStyle.FlatCap,
    StrokeCap.SQUARE: Qt.PenCapStyle.SquareCap,
    StrokeCap.ROUND: Qt.PenCapStyle.RoundCap,
}

STROKE_JOIN_MAP: dict[StrokeJoin, Qt.PenJoinStyle] = {
    StrokeJoin.MITER: Qt.PenJoinStyle.MiterJoin,
    StrokeJoin.BEVEL: Qt.PenJoinStyle.BevelJoin,
    StrokeJoin.ROUND: Qt.PenJoinStyle.RoundJoin,
}


def with_alpha(color: QColor, factor: float) -> QColor:
    """*color* with its alpha multiplied by *factor* (an opacity from 0.0 to 1.0)."""
    out = QColor(color)
    out.setAlphaF(out.alphaF() * max(0.0, min(1.0, factor)))
    return out


def _enum(kind: Any, raw: object, default: Any) -> Any:
    """The member of *kind* for *raw*; *default* when *raw* is absent or unknown."""
    if raw is None:
        return default
    try:
        return kind(raw)
    except ValueError:
        return default


def _clamp_unit(value: object, default: float = 1.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class VectorItem(ShadowMixin, SnapGraphicsItem):
    """Abstract base for vector-based annotation items.

    Provides the shared stroke, fill, opacity, and shadow properties and the
    serialization helpers. Concrete subclasses must implement ``boundingRect``,
    ``paint``, ``serialize``, and ``deserialize``.
    """

    def __init__(self, parent: SnapGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._init_shadow(
            enabled=False,
            color=DEFAULT_VECTOR_SHADOW_COLOR,
            offset=DEFAULT_VECTOR_SHADOW_OFFSET,
            blur=DEFAULT_VECTOR_SHADOW_BLUR,
        )
        self._stroke_color: QColor = QColor(DEFAULT_STROKE_COLOR)
        self._stroke_width: float = DEFAULT_STROKE_WIDTH
        self._stroke_style: BorderStyle = BorderStyle.SOLID
        self._stroke_cap: StrokeCap = StrokeCap.ROUND
        self._stroke_join: StrokeJoin = StrokeJoin.ROUND
        self._fill_color: QColor = QColor(DEFAULT_FILL_COLOR)
        self._fill_opacity: float = 1.0
        self._stroke_opacity: float = 1.0

    def _geometry_changed(self) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self.update()

    # --- stroke ---

    @property
    def stroke_color(self) -> QColor:
        return QColor(self._stroke_color)

    @stroke_color.setter
    def stroke_color(self, color: QColor) -> None:
        self._stroke_color = QColor(color)
        self.update()

    @property
    def stroke_width(self) -> float:
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, width: float) -> None:
        self._stroke_width = max(0.0, width)
        self._geometry_changed()

    @property
    def stroke_style(self) -> BorderStyle:
        """Solid, Dashed, Dotted, DashDot, or DashDotDot (Basic Shape PRD 2.2)."""
        return self._stroke_style

    @stroke_style.setter
    def stroke_style(self, value: BorderStyle) -> None:
        self._stroke_style = BorderStyle(value)
        self._geometry_changed()

    @property
    def stroke_cap(self) -> StrokeCap:
        """Flat, Square, or Round: line endpoints and dash caps (Basic Shape PRD 2.2)."""
        return self._stroke_cap

    @stroke_cap.setter
    def stroke_cap(self, value: StrokeCap) -> None:
        self._stroke_cap = StrokeCap(value)
        self._geometry_changed()

    @property
    def stroke_join(self) -> StrokeJoin:
        """Miter, Bevel, or Round: the corners of closed shapes (Basic Shape PRD 2.2)."""
        return self._stroke_join

    @stroke_join.setter
    def stroke_join(self, value: StrokeJoin) -> None:
        self._stroke_join = StrokeJoin(value)
        self._geometry_changed()

    @property
    def stroke_opacity(self) -> float:
        """Opacity of the stroke, border, or outline, 0.0 to 1.0; a render multiplier
        over the colour's own alpha (Technical Architecture PRD 3.9)."""
        return self._stroke_opacity

    @stroke_opacity.setter
    def stroke_opacity(self, value: float) -> None:
        self._stroke_opacity = _clamp_unit(value)
        self.update()

    # --- fill ---

    @property
    def fill_color(self) -> QColor:
        return QColor(self._fill_color)

    @fill_color.setter
    def fill_color(self, color: QColor) -> None:
        # shape() depends on whether the fill is transparent (see hit_shape).
        self._fill_color = QColor(color)
        self._geometry_changed()

    @property
    def fill_opacity(self) -> float:
        """Opacity of the fill or background, 0.0 to 1.0; a render multiplier over the
        colour's own alpha, so a fill at 0 is still a fill for hit testing (silence 4)."""
        return self._fill_opacity

    @fill_opacity.setter
    def fill_opacity(self, value: float) -> None:
        self._fill_opacity = _clamp_unit(value)
        self.update()

    # --- pen / brush ---

    def pen(self) -> QPen:
        """The stroke as a QPen: colour at ``stroke_opacity``, width, style, cap, join."""
        p = QPen(with_alpha(self._stroke_color, self._stroke_opacity), self._stroke_width)
        p.setStyle(STROKE_STYLE_MAP.get(self._stroke_style, Qt.PenStyle.SolidLine))
        p.setCapStyle(STROKE_CAP_MAP.get(self._stroke_cap, Qt.PenCapStyle.RoundCap))
        p.setJoinStyle(STROKE_JOIN_MAP.get(self._stroke_join, Qt.PenJoinStyle.RoundJoin))
        return p

    def brush(self) -> QBrush:
        """The fill as a QBrush: the fill colour at ``fill_opacity``."""
        return QBrush(with_alpha(self._fill_color, self._fill_opacity))

    def stroke_margin(self) -> float:
        """How far the stroke can reach beyond the geometry: half the width, or the whole
        width for a miter join or a square cap."""
        if self._stroke_join is StrokeJoin.MITER or self._stroke_cap is StrokeCap.SQUARE:
            return self._stroke_width
        return self._stroke_width / 2.0

    def stroke_outline(self, path: QPainterPath) -> QPainterPath:
        """The area the stroke of *path* covers, with the current width, cap, join, and
        dash pattern: the shape a line's shadow takes (Basic Shape PRD 3.6)."""
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._stroke_width, 0.1))
        stroker.setCapStyle(STROKE_CAP_MAP.get(self._stroke_cap, Qt.PenCapStyle.RoundCap))
        stroker.setJoinStyle(STROKE_JOIN_MAP.get(self._stroke_join, Qt.PenJoinStyle.RoundJoin))
        style = STROKE_STYLE_MAP.get(self._stroke_style, Qt.PenStyle.SolidLine)
        if style is not Qt.PenStyle.SolidLine:
            stroker.setDashPattern(style)
        return stroker.createStroke(path)

    def shadow_path(self, outline: QPainterPath, *, closed: bool = True) -> QPainterPath:
        """What the shadow duplicates: the stroke's area, plus the interior of a closed
        *outline* when the fill is not transparent."""
        if self._stroke_width <= 0.0:
            stroke = QPainterPath()
        else:
            stroke = self.stroke_outline(outline)
        if closed and self._fill_color.alpha() > 0:
            return outline.united(stroke)
        return stroke

    # --- creation defaults ---

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        """Take the shared keys a tool's ``creation_defaults`` carry (Basic Shape PRD 2.6);
        a key the tool does not carry leaves the item's own default."""
        if "stroke_color" in defaults:
            self._stroke_color = QColor(defaults["stroke_color"])
        if "fill_color" in defaults:
            self._fill_color = QColor(defaults["fill_color"])
        if "stroke_width" in defaults:
            self._stroke_width = max(0.0, float(defaults["stroke_width"]))
        style = defaults.get("stroke_style")
        if isinstance(style, BorderStyle):
            self._stroke_style = style
        cap = defaults.get("stroke_cap")
        if isinstance(cap, StrokeCap):
            self._stroke_cap = cap
        join = defaults.get("stroke_join")
        if isinstance(join, StrokeJoin):
            self._stroke_join = join
        if "fill_opacity" in defaults:
            self._fill_opacity = _clamp_unit(defaults["fill_opacity"])
        if "stroke_opacity" in defaults:
            self._stroke_opacity = _clamp_unit(defaults["stroke_opacity"])
        if "shadow_enabled" in defaults:
            self._shadow_enabled = bool(defaults["shadow_enabled"])
        if "blend_mode" in defaults:
            self._blend_mode = normalize_item_blend_mode(defaults["blend_mode"])
        self._geometry_changed()

    # --- hit testing ---

    HIT_PADDING: float = 4.0

    def hit_shape(self, outline: QPainterPath) -> QPainterPath:
        """Return the clickable area for a closed outline.

        Basic Shape Annotation Tools PRD, Sections 5.6 and 6.6: when ``fill_color``
        has an alpha greater than zero the whole interior is clickable; when the
        fill is transparent only a band around the outline is, ``stroke_width``
        plus 4 pixels wide, so an unfilled shape does not swallow clicks meant for
        whatever it surrounds.
        """
        if self._fill_color.alpha() > 0:
            return outline
        stroker = QPainterPathStroker()
        stroker.setWidth(self._stroke_width + self.HIT_PADDING)
        return stroker.createStroke(outline)

    # --- serialization helpers ---

    def _base_data(self) -> dict[str, Any]:
        data = {
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "opacity": self.opacity(),
            "transform": self._transform_entry(),
            "stroke_color": self._stroke_color.name(QColor.NameFormat.HexArgb),
            "stroke_width": self._stroke_width,
            "stroke_style": self._stroke_style.value,
            "stroke_cap": self._stroke_cap.value,
            "stroke_join": self._stroke_join.value,
            "fill_color": self._fill_color.name(QColor.NameFormat.HexArgb),
            "fill_opacity": self._fill_opacity,
            "stroke_opacity": self._stroke_opacity,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
        }
        data.update(self._item_entry())
        data.update(self._shadow_data())
        return data

    def _apply_base_data(self, data: dict[str, Any]) -> None:
        """Read the shared keys; a key an earlier build did not write reads as the
        item's default, so a file saved before this work loads unchanged."""
        self.item_id = data.get("item_id", self.item_id)
        self.layer_id = data.get("layer_id", "")
        pos = data.get("pos", [0, 0])
        self.setPos(pos[0], pos[1])
        self.setRotation(data.get("rotation", 0.0))
        self.setOpacity(data.get("opacity", 1.0))
        self._apply_transform_entry(data)
        self._stroke_color = QColor(data.get("stroke_color", DEFAULT_STROKE_COLOR))
        self._stroke_width = max(0.0, float(data.get("stroke_width", DEFAULT_STROKE_WIDTH)))
        self._stroke_style = _enum(BorderStyle, data.get("stroke_style"), self._stroke_style)
        self._stroke_cap = _enum(StrokeCap, data.get("stroke_cap"), self._stroke_cap)
        self._stroke_join = _enum(StrokeJoin, data.get("stroke_join"), self._stroke_join)
        self._fill_color = QColor(data.get("fill_color", DEFAULT_FILL_COLOR))
        self._fill_opacity = _clamp_unit(data.get("fill_opacity", 1.0))
        self._stroke_opacity = _clamp_unit(data.get("stroke_opacity", 1.0))
        self._flip_horizontal = data.get("flip_horizontal", False)
        self._flip_vertical = data.get("flip_vertical", False)
        self._apply_item_entry(data)
        self._apply_shadow_data(data)

    def scale_geometry(self, sx: float, sy: float) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self._stroke_width *= (sx + sy) / 2.0

    # --- still abstract ---

    def boundingRect(self) -> QRectF:
        raise NotImplementedError

    def paint(self, painter: Any, option: Any, widget: Any = None) -> None:
        raise NotImplementedError

    def serialize(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> VectorItem:
        raise NotImplementedError
