"""StampItem — a stamp from the library, rendered from its SVG (PRD Sections 3.5, 3.9, 5.2).

Numbered Steps, Stamps & Emoji PRD Section 3: the item names a stamp by ``stamp_id`` and
carries where it came from (``builtin``, ``custom``, or ``embedded``), the SVG text when
embedded, its display size (the larger side), the two recolour values, the colorizable flag
from the index, one ``opacity`` (Technical Architecture PRD 4.3; kickoff silence 5), the
flips of the base class, and the shadow of decision 1. A built-in stamp is written by id
only; a custom stamp is embedded on save; a stamp the library does not know renders the
missing-stamp placeholder (Section 7.2). The item's position is the stamp's centre.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtSvg import QSvgRenderer

from snapmock.config.constants import MARKER_MIN_HIT_SIZE
from snapmock.core.stamp_library import (
    BUILTIN,
    CUSTOM,
    DEFAULT_STAMP_SIZE,
    EMBEDDED,
    STAMP_SIZE_MAX,
    STAMP_SIZE_MIN,
    StampInfo,
    StampLibrary,
    stamp_library,
)
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.shadow import ShadowMixin

DEFAULT_STAMP_COLOR = "#CC0000"
DEFAULT_STAMP_SECONDARY_COLOR = "#FFFFFF"


def _clamp(value: float) -> float:
    return max(STAMP_SIZE_MIN, min(STAMP_SIZE_MAX, float(value)))


class StampItem(ShadowMixin, SnapGraphicsItem):
    """A stamp placed on the canvas, centred on its position."""

    def __init__(
        self,
        stamp_id: str = "",
        stamp_size: float = DEFAULT_STAMP_SIZE,
        parent: SnapGraphicsItem | None = None,
        *,
        library: StampLibrary | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_shadow(enabled=False)
        self._library = library
        self._stamp_id: str = stamp_id
        self._stamp_source: str = BUILTIN
        self._svg_data: str | None = None
        self._stamp_name: str = ""
        self._stamp_size: float = _clamp(stamp_size)
        self._stretch: float = 1.0
        """Width over height relative to the SVG's own aspect; 1 until a non-uniform resize."""
        self._stamp_color = QColor(DEFAULT_STAMP_COLOR)
        self._stamp_secondary_color = QColor(DEFAULT_STAMP_SECONDARY_COLOR)
        self._colorizable: bool = True
        self._default_size: float = DEFAULT_STAMP_SIZE
        self._aspect: float = 1.0
        if stamp_id:
            self._resolve(stamp_id, None, BUILTIN)

    # ------------------------------------------------------------ the library

    def _lib(self) -> StampLibrary:
        return self._library if self._library is not None else stamp_library()

    def set_stamp(self, info: StampInfo, svg: str | None = None) -> None:
        """Show *info*'s stamp (a pick from the library panel or a Change Stamp)."""
        self._stamp_id = info.id
        self._stamp_source = CUSTOM if info.source == CUSTOM else BUILTIN
        self._stamp_name = info.name
        self._colorizable = info.colorizable
        self._default_size = info.default_size
        self._svg_data = svg if svg is not None else self._lib().svg_data(info.id)
        self._update_aspect()
        self._changed()

    def stamp_state(self) -> dict[str, object]:
        """The fields a Change Stamp swaps (PRD 6.2), for the command's undo."""
        return {
            "stamp_id": self._stamp_id,
            "stamp_source": self._stamp_source,
            "svg_data": self._svg_data,
            "stamp_name": self._stamp_name,
            "colorizable": self._colorizable,
            "default_size": self._default_size,
        }

    def apply_stamp_state(self, state: dict[str, object]) -> None:
        self._stamp_id = str(state["stamp_id"])
        self._stamp_source = str(state["stamp_source"])
        svg = state["svg_data"]
        self._svg_data = svg if isinstance(svg, str) else None
        self._stamp_name = str(state["stamp_name"])
        self._colorizable = bool(state["colorizable"])
        self._default_size = float(state["default_size"])  # type: ignore[arg-type]
        self._update_aspect()
        self._changed()

    def _resolve(self, stamp_id: str, svg_data: str | None, source: str) -> None:
        """Section 7.2: the local library first, then embedded data, else the placeholder."""
        library = self._lib()
        info = library.stamp(stamp_id)
        if info is not None:
            self._stamp_source = CUSTOM if info.source == CUSTOM else BUILTIN
            self._stamp_name = info.name
            self._colorizable = info.colorizable
            self._default_size = info.default_size
            self._svg_data = library.svg_data(stamp_id)
        elif svg_data:
            self._stamp_source = EMBEDDED
            self._stamp_name = stamp_id.rsplit("/", 1)[-1].replace("-", " ").title()
            self._svg_data = svg_data
        else:
            self._stamp_source = source
            self._stamp_name = stamp_id.rsplit("/", 1)[-1].replace("-", " ").title()
            self._svg_data = None
        self._update_aspect()

    def _renderer(self) -> QSvgRenderer:
        library = self._lib()
        if not self._svg_data:
            return library.placeholder_renderer()
        return library.renderer(
            self._svg_data,
            self._stamp_color,
            self._stamp_secondary_color,
            colorizable=self._colorizable,
        )

    def _update_aspect(self) -> None:
        size = self._renderer().defaultSize()
        if size.width() > 0 and size.height() > 0:
            self._aspect = size.width() / size.height()
        else:
            self._aspect = 1.0

    def _changed(self) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self.update()

    # ------------------------------------------------------------ properties

    @property
    def stamp_id(self) -> str:
        return self._stamp_id

    @stamp_id.setter
    def stamp_id(self, value: str) -> None:
        self._stamp_id = str(value)
        self._resolve(self._stamp_id, None, BUILTIN)
        self._changed()

    @property
    def stamp_source(self) -> str:
        return self._stamp_source

    @property
    def svg_data(self) -> str | None:
        return self._svg_data

    @svg_data.setter
    def svg_data(self, value: str | None) -> None:
        self._svg_data = value or None
        if self._svg_data and self._lib().stamp(self._stamp_id) is None:
            self._stamp_source = EMBEDDED
        self._update_aspect()
        self._changed()

    @property
    def stamp_name(self) -> str:
        return self._stamp_name

    @property
    def is_missing(self) -> bool:
        """True when neither the library nor the file had the stamp's SVG (Section 7.2)."""
        return not self._svg_data

    @property
    def stamp_size(self) -> float:
        return self._stamp_size

    @stamp_size.setter
    def stamp_size(self, value: float) -> None:
        self._stamp_size = _clamp(value)
        self._changed()

    @property
    def default_size(self) -> float:
        """The index's default size for this stamp (Reset Size, kickoff silence 13)."""
        return self._default_size

    @property
    def stamp_color(self) -> QColor:
        return QColor(self._stamp_color)

    @stamp_color.setter
    def stamp_color(self, value: QColor) -> None:
        self._stamp_color = QColor(value)
        self.update()

    @property
    def stamp_secondary_color(self) -> QColor:
        return QColor(self._stamp_secondary_color)

    @stamp_secondary_color.setter
    def stamp_secondary_color(self, value: QColor) -> None:
        self._stamp_secondary_color = QColor(value)
        self.update()

    @property
    def colorizable(self) -> bool:
        return self._colorizable

    @colorizable.setter
    def colorizable(self, value: bool) -> None:
        self._colorizable = bool(value)
        self.update()

    # ------------------------------------------------------------ geometry

    def stamp_rect(self) -> QRectF:
        """The render rectangle, centred on the origin: the larger side is ``stamp_size``
        and the other follows the SVG's aspect, times the stretch of a non-uniform resize."""
        aspect = self._aspect * self._stretch
        if aspect >= 1.0:
            w, h = self._stamp_size, self._stamp_size / aspect
        else:
            w, h = self._stamp_size * aspect, self._stamp_size
        return QRectF(-w / 2, -h / 2, w, h)

    def _min_hit_rect(self) -> QRectF:
        half = MARKER_MIN_HIT_SIZE / 2
        return QRectF(-half, -half, MARKER_MIN_HIT_SIZE, MARKER_MIN_HIT_SIZE)

    def scale_geometry(self, sx: float, sy: float) -> None:
        """Uniform by default (the handles hold the ratio); a different *sx* and *sy* from
        the Property Panel's width or height stretch the stamp (Section 3.7)."""
        rect = self.stamp_rect()
        w, h = rect.width() * sx, rect.height() * sy
        if w <= 0 or h <= 0:
            return
        self._stamp_size = _clamp(max(w, h))
        self._stretch = (w / h) / self._aspect if self._aspect else 1.0
        self._shadow_cache_key = None
        self.prepareGeometryChange()

    def boundingRect(self) -> QRectF:
        rect = self.stamp_rect().adjusted(-1, -1, 1, 1)
        return rect.united(self.shadow_rect(rect)).united(self._min_hit_rect())

    def geometry_rect(self) -> QRectF:
        return QRectF(self.stamp_rect())

    def shape(self) -> QPainterPath:
        """The stamp's rectangle (Section 3.10), never smaller than 24 by 24 px."""
        path = QPainterPath()
        rect = self.stamp_rect()
        path.addRect(rect)
        if rect.width() < MARKER_MIN_HIT_SIZE or rect.height() < MARKER_MIN_HIT_SIZE:
            path.addRect(self._min_hit_rect())
        return path

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.stamp_rect()
        shadow_path = QPainterPath()
        shadow_path.addRect(rect)
        self.paint_shadow(painter, shadow_path)
        self._renderer().render(painter, rect)
        self._end_flip(painter)

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        """Section 7.2: a built-in stamp by id; a custom stamp embedded with its SVG."""
        embed = self._stamp_source in (CUSTOM, EMBEDDED) and bool(self._svg_data)
        data: dict[str, Any] = {
            "type": "StampItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "opacity": self.opacity(),
            "transform": self._transform_entry(),
            "stamp_id": self._stamp_id,
            "stamp_source": EMBEDDED if embed else self._stamp_source,
            "stamp_size": self._stamp_size,
            "stamp_color": self._stamp_color.name(QColor.NameFormat.HexArgb),
            "stamp_secondary_color": self._stamp_secondary_color.name(QColor.NameFormat.HexArgb),
            "colorizable": self._colorizable,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
        }
        if embed:
            data["svg_data"] = self._svg_data
        if self._stretch != 1.0:
            data["stamp_stretch"] = self._stretch
        data.update(self._shadow_data())
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> StampItem:
        item = cls()
        item.item_id = data.get("item_id", item.item_id)
        item.layer_id = data.get("layer_id", "")
        pos = data.get("pos", [0, 0])
        item.setPos(pos[0], pos[1])
        item.setRotation(float(data.get("rotation", 0.0)))
        item.setOpacity(float(data.get("opacity", 1.0)))
        item._apply_transform_entry(data)
        item._stamp_id = str(data.get("stamp_id", ""))
        item._stamp_size = _clamp(float(data.get("stamp_size", DEFAULT_STAMP_SIZE)))
        try:
            item._stretch = float(data.get("stamp_stretch", 1.0)) or 1.0
        except (TypeError, ValueError):
            item._stretch = 1.0
        item._stamp_color = QColor(str(data.get("stamp_color", DEFAULT_STAMP_COLOR)))
        item._stamp_secondary_color = QColor(
            str(data.get("stamp_secondary_color", DEFAULT_STAMP_SECONDARY_COLOR))
        )
        item._flip_horizontal = bool(data.get("flip_horizontal", False))
        item._flip_vertical = bool(data.get("flip_vertical", False))
        item._apply_blend_entry(data)
        item._apply_shadow_data(data)
        svg = data.get("svg_data")
        source = str(data.get("stamp_source", BUILTIN))
        item._resolve(item._stamp_id, svg if isinstance(svg, str) else None, source)
        if item._stamp_source == EMBEDDED and "colorizable" in data:
            # The index is not there to say; the file's flag stands
            item._colorizable = bool(data["colorizable"])
        return item

    @property
    def type_name(self) -> str:
        return "Stamp"
