"""EmojiItem — a Unicode emoji drawn in the platform's colour emoji font (PRD Sections 4.4, 4.7).

Numbered Steps, Stamps & Emoji PRD Section 4: the item stores the emoji's character
sequence (a skin-tone modifier or zero-width-joiner sequence kept whole, Section 7.3), its
name for display and search, its size (the square's side, 16 to 256 px), the skin tone as a
separate property that is also part of the sequence, one ``opacity`` (Technical Architecture
PRD 4.3), the flips of the base class, and the shadow of decision 1. Rendering is
``QPainter.drawText`` in the family ``emoji_font_family()`` names, centred in the square;
the project file keeps the code points, so another platform shows its own design.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath

from snapmock.config.constants import MARKER_MIN_HIT_SIZE
from snapmock.core.emoji_data import (
    DEFAULT_EMOJI_SIZE,
    EMOJI_SIZE_MAX,
    EMOJI_SIZE_MIN,
    SkinTone,
    emoji_data,
    emoji_font_family,
    skin_tone_of,
    strip_skin_tone,
)
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.shadow import ShadowMixin

GLYPH_SHARE = 0.9
"""The font pixel size as a share of the square: colour emoji glyphs fill about the em box."""
SHADOW_INSET = 0.08
"""The shadow is a rounded square inset by this share, since colour glyphs have no outline."""

_font_family_cache: str | None = None
_font_family_checked = False


def resolved_emoji_family() -> str | None:
    """``emoji_font_family()`` looked up once per process."""
    global _font_family_cache, _font_family_checked
    if not _font_family_checked:
        _font_family_cache = emoji_font_family()
        _font_family_checked = True
    return _font_family_cache


def reset_emoji_font_cache() -> None:
    """Forget the looked-up family (tests)."""
    global _font_family_cache, _font_family_checked
    _font_family_cache = None
    _font_family_checked = False


def _clamp(value: float) -> float:
    return max(EMOJI_SIZE_MIN, min(EMOJI_SIZE_MAX, float(value)))


class EmojiItem(ShadowMixin, SnapGraphicsItem):
    """An emoji placed on the canvas, centred on its position."""

    def __init__(
        self,
        emoji_char: str = "",
        emoji_size: float = DEFAULT_EMOJI_SIZE,
        parent: SnapGraphicsItem | None = None,
        *,
        emoji_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_shadow(enabled=False)
        self._emoji_char: str = emoji_char
        self._emoji_name: str = (
            emoji_name if emoji_name is not None else emoji_data().name_of(emoji_char)
        )
        self._emoji_size: float = _clamp(emoji_size)
        self._skin_tone: SkinTone = skin_tone_of(emoji_char)

    def _changed(self) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self.update()

    # ------------------------------------------------------------ properties

    @property
    def emoji_char(self) -> str:
        return self._emoji_char

    @emoji_char.setter
    def emoji_char(self, value: str) -> None:
        self._emoji_char = str(value)
        self._skin_tone = skin_tone_of(self._emoji_char)
        self.update()

    @property
    def emoji_name(self) -> str:
        return self._emoji_name

    @emoji_name.setter
    def emoji_name(self, value: str) -> None:
        self._emoji_name = str(value)

    def set_emoji(self, emoji_char: str, emoji_name: str | None = None) -> None:
        """Show *emoji_char* (a pick from the picker or a Change Emoji); the name from the
        data when not given; the tone read from the sequence."""
        self._emoji_char = emoji_char
        self._emoji_name = (
            emoji_name if emoji_name is not None else emoji_data().name_of(emoji_char)
        )
        self._skin_tone = skin_tone_of(emoji_char)
        self._changed()

    @property
    def emoji_size(self) -> float:
        return self._emoji_size

    @emoji_size.setter
    def emoji_size(self, value: float) -> None:
        self._emoji_size = _clamp(value)
        self._changed()

    @property
    def skin_tone(self) -> SkinTone:
        return self._skin_tone

    @skin_tone.setter
    def skin_tone(self, value: SkinTone) -> None:
        """Re-tone the sequence where the data says (Section 7.3); a tone on an emoji that
        takes none leaves the sequence alone."""
        tone = SkinTone(value)
        self._skin_tone = tone
        self._emoji_char = emoji_data().toned(self._emoji_char, tone)
        self.update()

    @property
    def supports_skin_tones(self) -> bool:
        info = emoji_data().lookup(self._emoji_char)
        return info is not None and info.skin_tones

    @property
    def base_char(self) -> str:
        """The sequence without its skin tone."""
        return strip_skin_tone(self._emoji_char)

    # ------------------------------------------------------------ geometry

    def emoji_rect(self) -> QRectF:
        half = self._emoji_size / 2
        return QRectF(-half, -half, self._emoji_size, self._emoji_size)

    def _min_hit_rect(self) -> QRectF:
        half = MARKER_MIN_HIT_SIZE / 2
        return QRectF(-half, -half, MARKER_MIN_HIT_SIZE, MARKER_MIN_HIT_SIZE)

    def scale_geometry(self, sx: float, sy: float) -> None:
        self._emoji_size = _clamp(self._emoji_size * (sx + sy) / 2.0)
        self._shadow_cache_key = None
        self.prepareGeometryChange()

    def boundingRect(self) -> QRectF:
        rect = self.emoji_rect().adjusted(-1, -1, 1, 1)
        return rect.united(self.shadow_rect(rect)).united(self._min_hit_rect())

    def geometry_rect(self) -> QRectF:
        return QRectF(self.emoji_rect())

    def shape(self) -> QPainterPath:
        """The square (Section 4.8), never smaller than 24 by 24 px."""
        path = QPainterPath()
        rect = self.emoji_rect()
        path.addRect(rect)
        if rect.width() < MARKER_MIN_HIT_SIZE:
            path.addRect(self._min_hit_rect())
        return path

    def font(self) -> QFont:
        """The emoji font at the size that fills the square (Section 4.7)."""
        family = resolved_emoji_family()
        font = QFont(family) if family else QFont()
        font.setPixelSize(max(1, int(round(self._emoji_size * GLYPH_SHARE))))
        return font

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = self.emoji_rect()
        if self._shadow_enabled:
            inset = self._emoji_size * SHADOW_INSET
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                rect.adjusted(inset, inset, -inset, -inset), inset * 2, inset * 2
            )
            self.paint_shadow(painter, shadow_path)
        if self._emoji_char:
            painter.setFont(self.font())
            painter.setPen(QColor(Qt.GlobalColor.black))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._emoji_char)
        self._end_flip(painter)

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "EmojiItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "opacity": self.opacity(),
            "transform": self._transform_entry(),
            "emoji_char": self._emoji_char,
            "emoji_name": self._emoji_name,
            "emoji_size": self._emoji_size,
            "skin_tone": self._skin_tone.value,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
        }
        data.update(self._shadow_data())
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> EmojiItem:
        chars = str(data.get("emoji_char", ""))
        name = data.get("emoji_name")
        item = cls(chars, emoji_name=str(name) if isinstance(name, str) and name else None)
        item.item_id = data.get("item_id", item.item_id)
        item.layer_id = data.get("layer_id", "")
        pos = data.get("pos", [0, 0])
        item.setPos(pos[0], pos[1])
        item.setRotation(float(data.get("rotation", 0.0)))
        item.setOpacity(float(data.get("opacity", 1.0)))
        item._apply_transform_entry(data)
        item._emoji_size = _clamp(float(data.get("emoji_size", DEFAULT_EMOJI_SIZE)))
        item._flip_horizontal = bool(data.get("flip_horizontal", False))
        item._flip_vertical = bool(data.get("flip_vertical", False))
        item._apply_blend_entry(data)
        item._apply_shadow_data(data)
        # Section 7.3: the tone is in the sequence; the property rebuilds it when they differ
        try:
            tone = SkinTone(str(data.get("skin_tone", item._skin_tone.value)))
        except ValueError:
            tone = item._skin_tone
        if tone is not item._skin_tone:
            item.skin_tone = tone
        return item

    @property
    def type_name(self) -> str:
        return "Emoji"
