"""NumberedStepItem — a badge with a sequential number and an optional label line.

Numbered Steps, Stamps & Emoji PRD Section 2: the item is a :class:`VectorItem` (Technical
Architecture PRD 4.2) whose fill colour is the badge colour and whose stroke is the
border, with the eight badge shapes of Section 2.5, the display modes of Section 2.3, the
label line of Section 2.6, the shadow of decision 1, and the hit area of Section 2.10.
The item's position is the badge centre, or the pin's point for the pin shape.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

from snapmock.config.constants import (
    BADGE_SIZE_MAX,
    BADGE_SIZE_MIN,
    DEFAULT_BADGE_BORDER_COLOR,
    DEFAULT_BADGE_BORDER_WIDTH,
    DEFAULT_BADGE_COLOR,
    DEFAULT_BADGE_FONT_FAMILY,
    DEFAULT_BADGE_SIZE,
    DEFAULT_BADGE_TEXT_COLOR,
    DEFAULT_LABEL_BACKGROUND,
    DEFAULT_LABEL_COLOR,
    DEFAULT_LABEL_FONT_SIZE,
    MARKER_MIN_HIT_SIZE,
    BadgeShape,
    BorderStyle,
    DisplayMode,
    FontWeight,
    LabelPosition,
)
from snapmock.items.vector_item import VectorItem, with_alpha

_LABEL_GAP = 6.0
"""Pixels between the badge edge and the label box (Section 2.6)."""
_AUTO_FONT_RATIO = 0.55
"""Auto font size as a share of the badge size for a single digit (Section 2.9)."""
_REFERENCE_PIXEL_SIZE = 100.0

# The share of the badge size the text may fill, per shape, as (width, height).
_INTERIOR: dict[BadgeShape, tuple[float, float]] = {
    BadgeShape.CIRCLE: (0.72, 0.72),
    BadgeShape.ROUNDED_SQUARE: (0.82, 0.82),
    BadgeShape.SQUARE: (0.86, 0.86),
    BadgeShape.DIAMOND: (0.5, 0.5),
    BadgeShape.HEXAGON: (0.72, 0.72),
    BadgeShape.STAR: (0.42, 0.42),
    BadgeShape.OVAL: (0.8, 0.52),
    BadgeShape.PIN: (0.72, 0.72),
}

_ROMAN: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def letter_for(number: int) -> str:
    """1 is A, 26 is Z, 27 is AA (Section 2.3); zero and below print as digits."""
    if number <= 0:
        return str(number)
    letters = ""
    n = number
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def roman_for(number: int) -> str:
    """The Roman numeral for 1 to 3999; digits outside that range."""
    if number <= 0 or number >= 4000:
        return str(number)
    out = ""
    n = number
    for value, glyph in _ROMAN:
        while n >= value:
            out += glyph
            n -= value
    return out


class NumberedStepItem(VectorItem):
    """A step badge: shape, number or text, border, shadow, and an optional label.

    The border style, the fill and stroke opacities, and the shadow are the vector base's
    (Vector Item Properties work); the shadow keeps the marker PRD's defaults and is on
    by default (Section 2.4).
    """

    def __init__(
        self,
        number_value: int = 1,
        badge_size: float = DEFAULT_BADGE_SIZE,
        parent: VectorItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_shadow(enabled=True)  # the marker PRD's defaults over the vector base's
        self._number_value: int = int(number_value)
        self._display_mode: DisplayMode = DisplayMode.NUMBER
        self._custom_text: str = ""
        self._badge_shape: BadgeShape = BadgeShape.CIRCLE
        self._badge_size: float = self._clamp_size(badge_size)
        self._text_color: QColor = QColor(DEFAULT_BADGE_TEXT_COLOR)
        self._font_family: str = DEFAULT_BADGE_FONT_FAMILY
        self._font_size: float = 0.0
        self._font_weight: FontWeight = FontWeight.BOLD
        self._label_text: str = ""
        self._label_position: LabelPosition = LabelPosition.RIGHT
        self._label_font_size: float = DEFAULT_LABEL_FONT_SIZE
        self._label_color: QColor = QColor(DEFAULT_LABEL_COLOR)
        self._label_background: QColor = QColor(DEFAULT_LABEL_BACKGROUND)
        self._label_background_enabled: bool = False
        # The badge colour is the fill and the border is the stroke (Section 2.1).
        self._fill_color = QColor(DEFAULT_BADGE_COLOR)
        self._stroke_color = QColor(DEFAULT_BADGE_BORDER_COLOR)
        self._stroke_width = DEFAULT_BADGE_BORDER_WIDTH

    @staticmethod
    def _clamp_size(value: float) -> float:
        return max(BADGE_SIZE_MIN, min(BADGE_SIZE_MAX, float(value)))

    def _changed(self) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self.update()

    # ------------------------------------------------------------ the number

    @property
    def number_value(self) -> int:
        return self._number_value

    @number_value.setter
    def number_value(self, value: int) -> None:
        self._number_value = int(value)
        self._changed()

    @property
    def display_mode(self) -> DisplayMode:
        return self._display_mode

    @display_mode.setter
    def display_mode(self, value: DisplayMode) -> None:
        self._display_mode = DisplayMode(value)
        self._changed()

    @property
    def custom_text(self) -> str:
        return self._custom_text

    @custom_text.setter
    def custom_text(self, value: str) -> None:
        self._custom_text = str(value)
        self._changed()

    def display_string(self) -> str:
        """The text the badge shows for the current mode (Section 2.3)."""
        mode = self._display_mode
        if mode is DisplayMode.TEXT:
            return self._custom_text
        if mode is DisplayMode.LETTER:
            return letter_for(self._number_value)
        if mode is DisplayMode.ROMAN:
            return roman_for(self._number_value)
        return str(self._number_value)

    # ------------------------------------------------------------ the badge

    @property
    def badge_shape(self) -> BadgeShape:
        return self._badge_shape

    @badge_shape.setter
    def badge_shape(self, value: BadgeShape) -> None:
        self._badge_shape = BadgeShape(value)
        self._changed()

    @property
    def badge_color(self) -> QColor:
        """The badge fill (Section 2.4); the same value as ``fill_color``."""
        return QColor(self._fill_color)

    @badge_color.setter
    def badge_color(self, value: QColor) -> None:
        self.fill_color = value

    @property
    def badge_size(self) -> float:
        return self._badge_size

    @badge_size.setter
    def badge_size(self, value: float) -> None:
        self._badge_size = self._clamp_size(value)
        self._changed()

    @property
    def text_color(self) -> QColor:
        return QColor(self._text_color)

    @text_color.setter
    def text_color(self, value: QColor) -> None:
        self._text_color = QColor(value)
        self.update()

    @property
    def font_family(self) -> str:
        return self._font_family

    @font_family.setter
    def font_family(self, value: str) -> None:
        self._font_family = str(value)
        self._changed()

    @property
    def font_size(self) -> float:
        """Points; 0 means auto-sized to the badge (Section 2.4)."""
        return self._font_size

    @font_size.setter
    def font_size(self, value: float) -> None:
        self._font_size = max(0.0, float(value))
        self._changed()

    @property
    def font_weight(self) -> FontWeight:
        return self._font_weight

    @font_weight.setter
    def font_weight(self, value: FontWeight) -> None:
        self._font_weight = FontWeight(value)
        self._changed()

    @property
    def border_color(self) -> QColor:
        """The badge border (Section 2.4); the same value as ``stroke_color``."""
        return QColor(self._stroke_color)

    @border_color.setter
    def border_color(self, value: QColor) -> None:
        self.stroke_color = value

    @property
    def border_width(self) -> float:
        return self._stroke_width

    @border_width.setter
    def border_width(self, value: float) -> None:
        self.stroke_width = value

    @property
    def border_style(self) -> BorderStyle:
        """The badge border's style (Section 2.4); the same value as ``stroke_style``."""
        return self._stroke_style

    @border_style.setter
    def border_style(self, value: BorderStyle) -> None:
        self.stroke_style = value

    # ------------------------------------------------------------ the label

    @property
    def label_text(self) -> str:
        return self._label_text

    @label_text.setter
    def label_text(self, value: str) -> None:
        self._label_text = str(value)
        self._changed()

    @property
    def label_position(self) -> LabelPosition:
        return self._label_position

    @label_position.setter
    def label_position(self, value: LabelPosition) -> None:
        self._label_position = LabelPosition(value)
        self._changed()

    @property
    def label_font_size(self) -> float:
        return self._label_font_size

    @label_font_size.setter
    def label_font_size(self, value: float) -> None:
        self._label_font_size = max(1.0, float(value))
        self._changed()

    @property
    def label_color(self) -> QColor:
        return QColor(self._label_color)

    @label_color.setter
    def label_color(self, value: QColor) -> None:
        self._label_color = QColor(value)
        self.update()

    @property
    def label_background(self) -> QColor:
        return QColor(self._label_background)

    @label_background.setter
    def label_background(self, value: QColor) -> None:
        self._label_background = QColor(value)
        self.update()

    @property
    def label_background_enabled(self) -> bool:
        return self._label_background_enabled

    @label_background_enabled.setter
    def label_background_enabled(self, value: bool) -> None:
        self._label_background_enabled = bool(value)
        self._changed()

    # ------------------------------------------------------------ geometry

    def badge_center(self) -> QPointF:
        """The centre of the badge body: the origin, or the pin's head (Section 2.9)."""
        if self._badge_shape is BadgeShape.PIN:
            return QPointF(0.0, -self._badge_size)
        return QPointF(0.0, 0.0)

    def badge_rect(self) -> QRectF:
        """The badge body's rectangle in item coordinates (the head, for the pin)."""
        s = self._badge_size
        c = self.badge_center()
        if self._badge_shape is BadgeShape.OVAL:
            return QRectF(c.x() - s / 2, c.y() - s * 0.35, s, s * 0.7)
        return QRectF(c.x() - s / 2, c.y() - s / 2, s, s)

    def badge_path(self) -> QPainterPath:
        """The badge outline for the current shape (Section 2.5)."""
        r = self.badge_rect()
        s = self._badge_size
        path = QPainterPath()
        shape = self._badge_shape
        if shape is BadgeShape.CIRCLE or shape is BadgeShape.OVAL:
            path.addEllipse(r)
        elif shape is BadgeShape.ROUNDED_SQUARE:
            path.addRoundedRect(r, s * 0.2, s * 0.2)
        elif shape is BadgeShape.SQUARE:
            path.addRect(r)
        elif shape is BadgeShape.DIAMOND:
            c = r.center()
            h = s / 2
            path.addPolygon(
                QPolygonF(
                    [
                        QPointF(c.x(), c.y() - h),
                        QPointF(c.x() + h, c.y()),
                        QPointF(c.x(), c.y() + h),
                        QPointF(c.x() - h, c.y()),
                    ]
                )
            )
            path.closeSubpath()
        elif shape is BadgeShape.HEXAGON:
            c = r.center()
            radius = s / 2
            points = [
                QPointF(
                    c.x() + radius * math.cos(math.radians(60 * k)),
                    c.y() + radius * math.sin(math.radians(60 * k)),
                )
                for k in range(6)
            ]
            path.addPolygon(QPolygonF(points))
            path.closeSubpath()
        elif shape is BadgeShape.STAR:
            c = r.center()
            outer = s / 2
            inner = outer * 0.45
            points = []
            for k in range(10):
                radius = outer if k % 2 == 0 else inner
                angle = math.radians(-90 + 36 * k)
                points.append(
                    QPointF(c.x() + radius * math.cos(angle), c.y() + radius * math.sin(angle))
                )
            path.addPolygon(QPolygonF(points))
            path.closeSubpath()
        elif shape is BadgeShape.PIN:
            head = QPainterPath()
            head.addEllipse(r)
            c = r.center()
            radius = s / 2
            angle = math.radians(35)
            tail = QPainterPath(QPointF(0.0, 0.0))
            tail.lineTo(c.x() - radius * math.sin(angle), c.y() + radius * math.cos(angle))
            tail.lineTo(c.x() + radius * math.sin(angle), c.y() + radius * math.cos(angle))
            tail.closeSubpath()
            path = head.united(tail)
        return path

    def _badge_font(self) -> QFont:
        font = QFont(self._font_family)
        font.setBold(self._font_weight is FontWeight.BOLD)
        if self._font_size > 0:
            font.setPointSizeF(self._font_size)
        else:
            font.setPixelSize(max(1, int(round(self.auto_font_pixel_size()))))
        return font

    def auto_font_pixel_size(self) -> float:
        """The largest pixel size at which the display string fits the badge interior.

        Section 2.9: about ``badge_size * 0.55`` for a single digit, smaller for longer
        strings, measured with the font's metrics at a reference size and scaled.
        """
        text = self.display_string() or "0"
        share_w, share_h = _INTERIOR[self._badge_shape]
        interior_w = self._badge_size * share_w
        interior_h = self._badge_size * share_h
        font = QFont(self._font_family)
        font.setBold(self._font_weight is FontWeight.BOLD)
        font.setPixelSize(int(_REFERENCE_PIXEL_SIZE))
        metrics = QFontMetricsF(font)
        width = max(1.0, metrics.horizontalAdvance(text))
        height = max(1.0, metrics.capHeight() * 1.25)
        by_width = _REFERENCE_PIXEL_SIZE * interior_w / width
        by_height = _REFERENCE_PIXEL_SIZE * interior_h / height
        return max(4.0, min(self._badge_size * _AUTO_FONT_RATIO, by_width, by_height))

    def _label_font(self) -> QFont:
        font = QFont(self._font_family)
        font.setPointSizeF(self._label_font_size)
        return font

    def _label_padding(self) -> float:
        return self._label_font_size * 0.4 if self._label_background_enabled else 1.0

    def label_rect(self) -> QRectF:
        """The label box (text plus pill padding) in item coordinates; empty with no label."""
        if not self._label_text:
            return QRectF()
        metrics = QFontMetricsF(self._label_font())
        pad = self._label_padding()
        w = metrics.horizontalAdvance(self._label_text) + 2 * pad
        h = metrics.height() + 2 * pad
        badge = self.badge_rect().adjusted(
            -self._stroke_width / 2,
            -self._stroke_width / 2,
            self._stroke_width / 2,
            self._stroke_width / 2,
        )
        c = badge.center()
        pos = self._label_position
        if pos is LabelPosition.RIGHT:
            return QRectF(badge.right() + _LABEL_GAP, c.y() - h / 2, w, h)
        if pos is LabelPosition.LEFT:
            return QRectF(badge.left() - _LABEL_GAP - w, c.y() - h / 2, w, h)
        if pos is LabelPosition.TOP:
            return QRectF(c.x() - w / 2, badge.top() - _LABEL_GAP - h, w, h)
        return QRectF(c.x() - w / 2, badge.bottom() + _LABEL_GAP, w, h)

    def _connector(self) -> tuple[QPointF, QPointF]:
        """The connecting line's ends: the badge edge and the facing label edge."""
        badge = self.badge_rect()
        label = self.label_rect()
        c = badge.center()
        pos = self._label_position
        if pos is LabelPosition.RIGHT:
            return QPointF(badge.right(), c.y()), QPointF(label.left(), label.center().y())
        if pos is LabelPosition.LEFT:
            return QPointF(badge.left(), c.y()), QPointF(label.right(), label.center().y())
        if pos is LabelPosition.TOP:
            return QPointF(c.x(), badge.top()), QPointF(label.center().x(), label.bottom())
        return QPointF(c.x(), badge.bottom()), QPointF(label.center().x(), label.top())

    def _min_hit_rect(self) -> QRectF:
        c = self.badge_center()
        half = MARKER_MIN_HIT_SIZE / 2
        return QRectF(c.x() - half, c.y() - half, MARKER_MIN_HIT_SIZE, MARKER_MIN_HIT_SIZE)

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)
        factor = (sx + sy) / 2.0
        self._badge_size = self._clamp_size(self._badge_size * factor)
        self._label_font_size = max(1.0, self._label_font_size * factor)
        if self._font_size > 0:
            self._font_size *= factor
        self._shadow_cache_key = None

    # ------------------------------------------------------------ QGraphicsItem

    def geometry_rect(self) -> QRectF:
        return self.badge_path().boundingRect()

    def boundingRect(self) -> QRectF:
        half = self._stroke_width / 2 + 1.0
        body = self.badge_path().boundingRect().adjusted(-half, -half, half, half)
        rect = body.united(self.shadow_rect(body)).united(self._min_hit_rect())
        label = self.label_rect()
        if not label.isNull():
            rect = rect.united(label.adjusted(-1, -1, 1, 1))
        return rect

    def shape(self) -> QPainterPath:
        """The badge (head and tail for the pin), the label box, and the 24 px minimum."""
        path = QPainterPath(self.badge_path())
        label = self.label_rect()
        if not label.isNull():
            path.addRect(label)
        body = self.badge_path().boundingRect()
        if body.width() < MARKER_MIN_HIT_SIZE or body.height() < MARKER_MIN_HIT_SIZE:
            path.addRect(self._min_hit_rect())
        return path

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        path = self.badge_path()
        self.paint_shadow(painter, path)
        # The fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush())
        painter.drawPath(path)
        # The border
        if self._stroke_width > 0:
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        # The number or text, centred in the badge body
        text = self.display_string()
        if text:
            painter.setFont(self._badge_font())
            painter.setPen(with_alpha(self._text_color, self._fill_opacity))
            painter.drawText(self.badge_rect(), Qt.AlignmentFlag.AlignCenter, text)
        # The label line
        if self._label_text:
            start, end = self._connector()
            line_pen = QPen(with_alpha(self._fill_color, 0.5), 1.0)
            line_pen.setCosmetic(True)
            painter.setPen(line_pen)
            painter.drawLine(start, end)
            label = self.label_rect()
            if self._label_background_enabled:
                radius = self._label_font_size * 0.5
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._label_background))
                painter.drawRoundedRect(label, radius, radius)
            painter.setFont(self._label_font())
            painter.setPen(with_alpha(self._label_color, self._fill_opacity))
            painter.drawText(label, Qt.AlignmentFlag.AlignCenter, self._label_text)
        self._end_flip(painter)

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        # The badge colour, border, and border style are the Section 5 keys, not the
        # vector base's; the base's cap and join keys stay (the badge takes the defaults).
        for key in ("stroke_color", "stroke_width", "fill_color", "stroke_style"):
            data.pop(key, None)
        data.update(
            {
                "type": "NumberedStepItem",
                "number_value": self._number_value,
                "display_mode": self._display_mode.value,
                "custom_text": self._custom_text,
                "badge_shape": self._badge_shape.value,
                "badge_color": self._fill_color.name(QColor.NameFormat.HexArgb),
                "badge_size": self._badge_size,
                "text_color": self._text_color.name(QColor.NameFormat.HexArgb),
                "font_family": self._font_family,
                "font_size": self._font_size,
                "font_weight": self._font_weight.value,
                "border_color": self._stroke_color.name(QColor.NameFormat.HexArgb),
                "border_width": self._stroke_width,
                "border_style": self._stroke_style.value,
                "label_text": self._label_text,
                "label_position": self._label_position.value,
                "label_font_size": self._label_font_size,
                "label_color": self._label_color.name(QColor.NameFormat.HexArgb),
                "label_background": self._label_background.name(QColor.NameFormat.HexArgb),
                "label_background_enabled": self._label_background_enabled,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> NumberedStepItem:
        # ``number`` and ``bg_color`` are the first-pass stub's keys (kickoff silence 2).
        item = cls(number_value=int(data.get("number_value", data.get("number", 1))))
        item._apply_base_data(data)
        item._fill_color = QColor(
            str(data.get("badge_color", data.get("bg_color", DEFAULT_BADGE_COLOR)))
        )
        item._stroke_color = QColor(str(data.get("border_color", DEFAULT_BADGE_BORDER_COLOR)))
        item._stroke_width = max(0.0, float(data.get("border_width", DEFAULT_BADGE_BORDER_WIDTH)))
        item._display_mode = _enum(DisplayMode, data.get("display_mode"), DisplayMode.NUMBER)
        item._custom_text = str(data.get("custom_text", ""))
        item._badge_shape = _enum(BadgeShape, data.get("badge_shape"), BadgeShape.CIRCLE)
        item._badge_size = cls._clamp_size(float(data.get("badge_size", DEFAULT_BADGE_SIZE)))
        item._text_color = QColor(str(data.get("text_color", DEFAULT_BADGE_TEXT_COLOR)))
        item._font_family = str(data.get("font_family", DEFAULT_BADGE_FONT_FAMILY))
        item._font_size = max(0.0, float(data.get("font_size", 0.0)))
        item._font_weight = _enum(FontWeight, data.get("font_weight"), FontWeight.BOLD)
        item._stroke_style = _enum(BorderStyle, data.get("border_style"), BorderStyle.SOLID)
        item._label_text = str(data.get("label_text", ""))
        item._label_position = _enum(
            LabelPosition, data.get("label_position"), LabelPosition.RIGHT
        )
        item._label_font_size = max(
            1.0, float(data.get("label_font_size", DEFAULT_LABEL_FONT_SIZE))
        )
        item._label_color = QColor(str(data.get("label_color", DEFAULT_LABEL_COLOR)))
        item._label_background = QColor(
            str(data.get("label_background", DEFAULT_LABEL_BACKGROUND))
        )
        item._label_background_enabled = bool(data.get("label_background_enabled", False))
        return item

    @property
    def type_name(self) -> str:
        return "Numbered Step"


def _enum(kind: Any, raw: object, default: Any) -> Any:
    """The member of *kind* for *raw*; *default* when *raw* is absent or unknown."""
    if raw is None:
        return default
    try:
        return kind(raw)
    except ValueError:
        return default
