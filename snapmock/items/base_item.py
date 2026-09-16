"""SnapGraphicsItem — abstract base class for all scene annotation items."""

from __future__ import annotations

import uuid
from abc import abstractmethod
from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QTransform
from PyQt6.QtWidgets import QGraphicsObject

from snapmock.core.layer import DEFAULT_BLEND_MODE, composition_mode, normalize_item_blend_mode


def transform_to_list(transform: QTransform) -> list[float]:
    """The nine matrix values of *transform*, row by row (the ``transform`` entry)."""
    return [
        transform.m11(),
        transform.m12(),
        transform.m13(),
        transform.m21(),
        transform.m22(),
        transform.m23(),
        transform.m31(),
        transform.m32(),
        transform.m33(),
    ]


def transform_from_list(values: object) -> QTransform:
    """The transform of nine matrix values; the identity when *values* is not that."""
    if not isinstance(values, list) or len(values) != 9:
        return QTransform()
    try:
        m = [float(v) for v in values]
    except (TypeError, ValueError):
        return QTransform()
    return QTransform(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8])


class SnapGraphicsItem(QGraphicsObject):
    """Base class for every annotation item in the scene.

    Adds a stable UUID, layer association, and serialization hooks on top of
    QGraphicsObject (which provides signal support).
    """

    def __init__(self, parent: QGraphicsObject | None = None) -> None:
        super().__init__(parent)
        self._item_id: str = uuid.uuid4().hex
        self._layer_id: str = ""
        self._locked: bool = False
        self._flip_horizontal: bool = False
        self._flip_vertical: bool = False
        self._layer_opacity: float = 1.0
        self._layer_blend_mode: str = DEFAULT_BLEND_MODE
        self._blend_mode: str = DEFAULT_BLEND_MODE
        self._item_blend_active: bool = False
        self._paint_saved: bool = False
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    # --- identity ---

    @property
    def item_id(self) -> str:
        return self._item_id

    @item_id.setter
    def item_id(self, value: str) -> None:
        self._item_id = value

    @property
    def layer_id(self) -> str:
        return self._layer_id

    @layer_id.setter
    def layer_id(self, value: str) -> None:
        self._layer_id = value
        scene = self.scene()
        apply_state = getattr(scene, "apply_layer_state", None)
        if callable(apply_state):
            apply_state(self)

    @property
    def layer_opacity(self) -> float:
        """The owning layer's opacity, applied on top of the item's own (Tech Arch 3.9.1).

        Runtime state set by the scene; never serialized.
        """
        return self._layer_opacity

    @layer_opacity.setter
    def layer_opacity(self, value: float) -> None:
        self._layer_opacity = max(0.0, min(1.0, value))
        self.update()

    @property
    def layer_blend_mode(self) -> str:
        """The owning layer's blend mode, applied as this item's painter composition mode
        (follow-up decision 3, option B: per item, on the display and in every export alike).

        Runtime state set by the scene; never serialized.
        """
        return self._layer_blend_mode

    @layer_blend_mode.setter
    def layer_blend_mode(self, value: str) -> None:
        self._layer_blend_mode = value
        self.update()

    @property
    def blend_mode(self) -> str:
        """The item's own blend mode (Technical Architecture PRD 3.1.4), one of
        ``ITEM_BLEND_MODES``; applied as the painter composition mode when the layer's
        mode is Normal, the layer's otherwise (3.9; Vector Item Properties decision 4)."""
        return self._blend_mode

    @blend_mode.setter
    def blend_mode(self, value: str) -> None:
        self._blend_mode = normalize_item_blend_mode(value)
        self.update()

    @property
    def locked(self) -> bool:
        return self._locked

    @locked.setter
    def locked(self, value: bool) -> None:
        self._locked = value

    # --- flip properties ---

    @property
    def flip_horizontal(self) -> bool:
        return self._flip_horizontal

    @flip_horizontal.setter
    def flip_horizontal(self, value: bool) -> None:
        self._flip_horizontal = value
        self.update()

    @property
    def flip_vertical(self) -> bool:
        return self._flip_vertical

    @flip_vertical.setter
    def flip_vertical(self, value: bool) -> None:
        self._flip_vertical = value
        self.update()

    def _apply_flip(self, painter: QPainter) -> None:
        """Apply the layer opacity, the layer blend mode, and any flip transform.

        Call at the start of ``paint()``. The blend mode is the layer's, applied per item
        (Technical Architecture PRD 3.9 departure, follow-up decision 3): two overlapping
        items on one non-Normal layer blend twice.
        """
        layer_blended = self._layer_blend_mode != DEFAULT_BLEND_MODE
        self._item_blend_active = not layer_blended and self._blend_mode != DEFAULT_BLEND_MODE
        blended = layer_blended or self._item_blend_active
        self._paint_saved = (
            self._flip_horizontal or self._flip_vertical or self._layer_opacity < 1.0 or blended
        )
        if not self._paint_saved:
            return
        painter.save()
        if self._layer_opacity < 1.0:
            painter.setOpacity(painter.opacity() * self._layer_opacity)
        if layer_blended:
            painter.setCompositionMode(composition_mode(self._layer_blend_mode))
        elif self._item_blend_active:
            painter.setCompositionMode(composition_mode(self._blend_mode))
        if self._flip_horizontal or self._flip_vertical:
            br = self.boundingRect()
            cx = br.center().x()
            cy = br.center().y()
            painter.translate(cx, cy)
            painter.scale(
                -1.0 if self._flip_horizontal else 1.0,
                -1.0 if self._flip_vertical else 1.0,
            )
            painter.translate(-cx, -cy)

    def _end_flip(self, painter: QPainter) -> None:
        """Restore painter state after :meth:`_apply_flip`. Call at end of paint()."""
        if self._paint_saved:
            painter.restore()
            self._paint_saved = False
        self._item_blend_active = False

    def _blend_entry(self) -> dict[str, Any]:
        """The ``blend_mode`` key of a serialized item; absent reads as Normal."""
        return {"blend_mode": self._blend_mode}

    def _apply_blend_entry(self, data: dict[str, Any]) -> None:
        self._blend_mode = normalize_item_blend_mode(data.get("blend_mode", DEFAULT_BLEND_MODE))

    # --- position / transform property shims ---

    @property
    def pos_x(self) -> float:
        return self.pos().x()

    @pos_x.setter
    def pos_x(self, value: float) -> None:
        self.setPos(value, self.pos().y())

    @property
    def pos_y(self) -> float:
        return self.pos().y()

    @pos_y.setter
    def pos_y(self, value: float) -> None:
        self.setPos(self.pos().x(), value)

    @property
    def rotation_deg(self) -> float:
        return self.rotation()

    @rotation_deg.setter
    def rotation_deg(self, value: float) -> None:
        self.setRotation(value)

    @property
    def opacity_pct(self) -> float:
        return self.opacity() * 100.0

    @opacity_pct.setter
    def opacity_pct(self, value: float) -> None:
        self.setOpacity(max(0.0, min(100.0, value)) / 100.0)

    # --- required overrides ---

    @abstractmethod
    def boundingRect(self) -> QRectF: ...

    @abstractmethod
    def paint(
        self,
        painter: Any,
        option: Any,
        widget: Any = None,
    ) -> None: ...

    def shape(self) -> QPainterPath:
        """Return an accurate shape for hit testing (default: bounding rect)."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def geometry_rect(self) -> QRectF:
        """The item's own edges in local coordinates: the shape a user sees as the item,
        without the stroke's half width, the shadow, or the hit padding that widen
        :meth:`boundingRect`. Snapping works on this rectangle, so a snapped rectangle's
        line sits on the grid line and not half a stroke beside it (end-to-end pass
        decision 5, as Doug corrected it 09-16-26). The default is the bounding rect;
        every item with padding overrides it."""
        return self.boundingRect()

    def scene_geometry_rect(self) -> QRectF:
        """:meth:`geometry_rect` in scene coordinates (the box of it, under a rotation)."""
        return self.mapRectToScene(self.geometry_rect())

    # --- serialization ---

    @abstractmethod
    def serialize(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of item state."""

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict[str, Any]) -> SnapGraphicsItem:
        """Reconstruct an item from serialized data."""

    def _transform_entry(self) -> list[float]:
        """The ``transform`` entry every item's serialized form carries: the Qt transform
        the handles set on a resize, rotation, or skew (Technical Architecture PRD 6.1)."""
        return transform_to_list(self.transform())

    def _apply_transform_entry(self, data: dict[str, Any]) -> None:
        """Restore the transform from a serialized entry; the identity when absent."""
        self.setTransform(transform_from_list(data.get("transform")))

    def renew_ids(self) -> None:
        """Give this item a new id. A container also renews every item below it."""
        self._item_id = uuid.uuid4().hex

    def clone(self) -> SnapGraphicsItem:
        """Return a deep copy with a new item_id."""
        data = self.serialize()
        new_item = type(self).deserialize(data)
        new_item.renew_ids()
        return new_item

    # --- geometry scaling ---

    def scale_geometry(self, sx: float, sy: float) -> None:
        """Scale internal geometry by the given factors.

        Subclasses override to scale rects, paths, radii, etc. Default is no-op.
        """

    # --- type label for UI ---

    @property
    def type_name(self) -> str:
        return type(self).__name__
