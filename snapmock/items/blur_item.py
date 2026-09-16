"""BlurItem — a region that obscures what lies beneath it (Blur PRD Section 2).

Gaussian blur, pixelate, or solid fill (2.2) over a rectangle, optionally rounded, or an
ellipse (2.4), with a feathered edge, an inverted mask that obscures everything outside
the region, the item's opacity blending the result with the content beneath, and an
optional border (2.5). The result is rendered from what lies below the item through
``RenderEngine.render_below`` (2.7) and cached until the region, a property, the zoom (by
a factor of two), or the content below changes, the last read from the scene's content
revision (Basic Shape remainder silence 3).

A Freeform region carries an ``alpha_mask`` instead of a shape (freeform blur decision 1,
option A): a ``QImage`` in canvas pixels aligned to the region's rectangle, opaque where
the region obscures and transparent where it does not, which replaces the shape in the
render's clip and feathers and inverts exactly as a shape does. The rectangle follows the
painted bounds, a resize resamples the mask, and a rotation leaves it in the item's own
coordinates, where the capture already works.

The Whole Layer shape takes the canvas as its region, with nothing to drag (2.4), and
``source_mode`` with ``source_layer_id`` narrow what the capture reads to the active layer
or to one named layer (2.5). The background-thread render of 2.10 is not built. The class
keeps the name ``BlurItem`` that every saved file carries (the PRD's ``BlurRegionItem``).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem

from snapmock.config.constants import (
    BLUR_FEATHER_MAX,
    BLUR_PIXEL_SIZE_MAX,
    BLUR_PIXEL_SIZE_MIN,
    BLUR_RADIUS_MAX,
    BLUR_RADIUS_MIN,
    CORNER_RADIUS_MAX,
    DEFAULT_BLUR_FILL_COLOR,
    BlurMode,
    BlurRegionShape,
    BlurSourceMode,
)
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.mask_utils import (
    blank_mask,
    decode_mask_field,
    decode_mask_png,
    encode_mask_field,
    mask_file_reference,
    scaled_mask,
)
from snapmock.items.shadow import blur_image

_SCALE_MIN = 0.25
_SCALE_MAX = 4.0

GAUSSIAN_RENDER_SCALE = 0.5
"""The Gaussian captures and blurs at half size and scales the result back (2.10; freeform
blur decision 4, option A): about four times faster, so a 1000 by 1000 px region meets the
100 ms target, at the cost of a slightly softer result at the largest radii. 2.10's
background thread and progress indicator are not built."""

GAUSSIAN_HALF_SCALE_MIN_RADIUS = 4.0
"""Below this radius the Gaussian renders at full size. Halving the capture throws away
detail finer than two pixels, which a blur of radius 1 or 2 is meant to keep: 2.10's own
acceptance row asks that radius 1 stay barely noticeable. The 100 ms target is met from
this radius up."""


def _clamp(value: object, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _enum_or(kind: Any, raw: object, default: Any) -> Any:
    try:
        return kind(raw)
    except ValueError:
        return default


def pixelate_image(image: QImage, tile: int) -> QImage:
    """*image* as a mosaic of *tile* by *tile* squares, each its tile's average colour,
    tiles aligned to the top-left corner (2.7)."""
    tile = max(1, int(tile))
    if tile == 1 or image.isNull():
        return image.copy()
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    width, height = image.width(), image.height()
    pointer = image.bits()
    if pointer is None:
        return image.copy()
    pointer.setsize(image.sizeInBytes())
    raw = np.frombuffer(pointer.asstring(image.sizeInBytes()), dtype=np.uint8)
    pixels = raw.reshape(height, image.bytesPerLine())[:, : width * 4].reshape(height, width, 4)
    rows = math.ceil(height / tile)
    cols = math.ceil(width / tile)
    padded = np.pad(
        pixels.astype(np.float64),
        ((0, rows * tile - height), (0, cols * tile - width), (0, 0)),
        mode="edge",
    )
    means = padded.reshape(rows, tile, cols, tile, 4).mean(axis=(1, 3))
    mosaic = np.repeat(np.repeat(means, tile, axis=0), tile, axis=1)[:height, :width]
    out = np.ascontiguousarray(np.clip(np.rint(mosaic), 0, 255).astype(np.uint8))
    result = QImage(
        out.tobytes(), width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied
    )
    return result.copy()


class BlurItem(SnapGraphicsItem):
    """A region that obscures the content beneath it."""

    def __init__(
        self,
        rect: QRectF | None = None,
        blur_radius: float = 10.0,
        parent: SnapGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._rect = QRectF(rect) if rect is not None else QRectF(0, 0, 100, 100)
        self._blur_mode: BlurMode = BlurMode.GAUSSIAN
        self._region_shape: BlurRegionShape = BlurRegionShape.RECTANGLE
        self._blur_radius = _clamp(blur_radius, BLUR_RADIUS_MIN, BLUR_RADIUS_MAX, 10.0)
        self._pixel_size = 10
        self._fill_color = QColor(DEFAULT_BLUR_FILL_COLOR)
        self._corner_radius = 0.0
        self._feather = 0.0
        self._invert_mask = False
        self._alpha_mask: QImage | None = None
        self._source_mode: BlurSourceMode = BlurSourceMode.ALL_BELOW
        self._source_layer_id: str | None = None
        self._border_color = QColor(0, 0, 0, 0)
        self._border_width = 0.0
        self._cache_key: tuple[Any, ...] | None = None
        self._cache_image: QImage | None = None
        self._cache_rect = QRectF()
        self._watched: Any = None

    # ------------------------------------------------------------ properties

    def _changed(self) -> None:
        self._cache_key = None
        self.prepareGeometryChange()
        self.update()

    @property
    def rect(self) -> QRectF:
        return QRectF(self._rect)

    @rect.setter
    def rect(self, value: QRectF) -> None:
        self._rect = QRectF(value)
        self._changed()

    @property
    def blur_mode(self) -> BlurMode:
        """Gaussian, Pixelate, or Solid (2.2)."""
        return self._blur_mode

    @blur_mode.setter
    def blur_mode(self, value: BlurMode) -> None:
        self._blur_mode = BlurMode(value)
        self._changed()

    @property
    def region_shape(self) -> BlurRegionShape:
        """Rectangle, Ellipse, Freeform, or Whole Layer (2.4)."""
        return self._region_shape

    @region_shape.setter
    def region_shape(self, value: BlurRegionShape) -> None:
        self._region_shape = BlurRegionShape(value)
        self._changed()

    @property
    def blur_radius(self) -> float:
        """The Gaussian radius in pixels, 1 to 50 (2.5)."""
        return self._blur_radius

    @blur_radius.setter
    def blur_radius(self, value: float) -> None:
        self._blur_radius = _clamp(value, BLUR_RADIUS_MIN, BLUR_RADIUS_MAX, 10.0)
        self._changed()

    @property
    def pixel_size(self) -> int:
        """The mosaic tile in pixels, 2 to 100 (2.5)."""
        return self._pixel_size

    @pixel_size.setter
    def pixel_size(self, value: int) -> None:
        self._pixel_size = int(_clamp(value, BLUR_PIXEL_SIZE_MIN, BLUR_PIXEL_SIZE_MAX, 10))
        self._changed()

    @property
    def fill_color(self) -> QColor:
        """The Solid Fill colour (2.5)."""
        return QColor(self._fill_color)

    @fill_color.setter
    def fill_color(self, value: QColor) -> None:
        self._fill_color = QColor(value)
        self._changed()

    @property
    def corner_radius(self) -> float:
        """A rectangle region's corner radius, stored as set and drawn clamped to half the
        smaller side, as the Rectangle's is (2.5)."""
        return self._corner_radius

    @corner_radius.setter
    def corner_radius(self, value: float) -> None:
        self._corner_radius = _clamp(value, 0.0, CORNER_RADIUS_MAX, 0.0)
        self._changed()

    @property
    def feather(self) -> float:
        """The softened edge in pixels, 0 to 30 (2.5)."""
        return self._feather

    @feather.setter
    def feather(self, value: float) -> None:
        self._feather = _clamp(value, 0.0, BLUR_FEATHER_MAX, 0.0)
        self._changed()

    @property
    def invert_mask(self) -> bool:
        """True obscures everything outside the region instead (2.5, 2.7)."""
        return self._invert_mask

    @invert_mask.setter
    def invert_mask(self, value: bool) -> None:
        self._invert_mask = bool(value)
        self._changed()

    @property
    def alpha_mask(self) -> QImage | None:
        """A Freeform region's painted mask (2.5): canvas pixels aligned to the region's
        rectangle, opaque where the region obscures. None for every other shape."""
        return None if self._alpha_mask is None else self._alpha_mask.copy()

    @alpha_mask.setter
    def alpha_mask(self, value: QImage | None) -> None:
        if value is None or value.isNull():
            self._alpha_mask = None
        else:
            self._alpha_mask = value.copy()
        self._changed()

    def ensure_mask(self) -> QImage:
        """The mask to paint into, made to fit the region's rectangle if there is none."""
        rect = self._rect
        width, height = max(1, round(rect.width())), max(1, round(rect.height()))
        mask = self._alpha_mask
        if mask is None or mask.isNull():
            mask = blank_mask(width, height)
            self._alpha_mask = mask
        return mask

    @property
    def source_mode(self) -> BlurSourceMode:
        """What the region obscures: everything below it, the active layer, or one named
        layer (2.5)."""
        return self._source_mode

    @source_mode.setter
    def source_mode(self, value: BlurSourceMode) -> None:
        self._source_mode = BlurSourceMode(value)
        self._changed()

    @property
    def source_layer_id(self) -> str | None:
        """The layer Specific Layer reads; a layer that is gone falls back to all below."""
        return self._source_layer_id

    @source_layer_id.setter
    def source_layer_id(self, value: str | None) -> None:
        self._source_layer_id = str(value) if value else None
        self._changed()

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
        self._border_width = _clamp(value, 0.0, 50.0, 0.0)
        self._changed()

    # ------------------------------------------------------------ geometry

    def region_rect(self) -> QRectF:
        """The region's rectangle in item coordinates: the stored one, or the canvas for a
        Whole Layer region, which has nothing to drag (2.4)."""
        if self._region_shape is BlurRegionShape.WHOLE_LAYER:
            scene = self.scene()
            if scene is not None and hasattr(scene, "canvas_rect"):
                return self.mapRectFromScene(scene.canvas_rect)
        return QRectF(self._rect)

    def region_path(self) -> QPainterPath:
        """The region's shape in item coordinates: the rectangle, rounded when a corner
        radius is set, the ellipse, the painted mask's rectangle, or the canvas (2.4)."""
        path = QPainterPath()
        if self._region_shape is BlurRegionShape.WHOLE_LAYER:
            path.addRect(self.region_rect())
            return path
        if self._region_shape is BlurRegionShape.FREEFORM:
            # The mask itself shapes the effect (2.7); the rectangle is what is clicked
            # and what a border follows (2.9)
            path.addRect(self._rect)
            return path
        if self._region_shape is BlurRegionShape.ELLIPSE:
            path.addEllipse(self._rect)
            return path
        limit = min(self._rect.width(), self._rect.height()) / 2.0
        radius = max(0.0, min(self._corner_radius, limit))
        if radius > 0:
            path.addRoundedRect(self._rect, radius, radius)
        else:
            path.addRect(self._rect)
        return path

    def effect_rect(self) -> QRectF:
        """Where the effect is painted, in item coordinates: the region with its feather,
        or the whole canvas when the mask is inverted."""
        scene = self.scene()
        region = self.region_rect()
        if self._invert_mask and scene is not None and hasattr(scene, "canvas_rect"):
            return self.mapRectFromScene(scene.canvas_rect).united(region)
        f = self._feather
        return region.adjusted(-f, -f, f, f)

    def scale_geometry(self, sx: float, sy: float) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(
            self._rect.x() * sx,
            self._rect.y() * sy,
            self._rect.width() * sx,
            self._rect.height() * sy,
        )
        if self._alpha_mask is not None:
            self._alpha_mask = scaled_mask(
                self._alpha_mask,
                max(1, round(self._rect.width())),
                max(1, round(self._rect.height())),
            )
        factor = (sx + sy) / 2.0
        self._blur_radius = _clamp(
            self._blur_radius * factor, BLUR_RADIUS_MIN, BLUR_RADIUS_MAX, 10
        )
        self._corner_radius *= factor
        self._feather = _clamp(self._feather * factor, 0.0, BLUR_FEATHER_MAX, 0.0)
        self._cache_key = None

    def boundingRect(self) -> QRectF:
        b = self._border_width / 2.0 + 1.0
        return self.effect_rect().united(self.region_rect().adjusted(-b, -b, b, b))

    def geometry_rect(self) -> QRectF:
        return QRectF(self.region_rect())

    def shape(self) -> QPainterPath:
        """The region's own shape: a blur is always visible, so it needs no padding (2.9)."""
        return self.region_path()

    # ------------------------------------------------------------ keeping in step

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
            self._unwatch()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            self._watch()
        return super().itemChange(change, value)

    def _watch(self) -> None:
        scene = self.scene()
        stack = getattr(scene, "command_stack", None)
        if stack is not None:
            stack.stack_changed.connect(self._on_content_changed)
            self._watched = stack

    def _unwatch(self) -> None:
        if self._watched is not None:
            try:
                self._watched.stack_changed.disconnect(self._on_content_changed)
            except (TypeError, RuntimeError):
                pass
            self._watched = None

    def _on_content_changed(self) -> None:
        # Content below may have changed anywhere under the region: repaint all of it
        self.update()

    # ------------------------------------------------------------ rendering (2.7)

    @staticmethod
    def render_scale(painter: QPainter) -> float:
        """The painter's scale rounded to a power of two, so the cache is rebuilt when the
        zoom changes by a factor of two (2.7) and the result stays sharp."""
        scale = math.sqrt(abs(painter.worldTransform().determinant())) or 1.0
        scale = 2.0 ** round(math.log2(scale))
        return max(_SCALE_MIN, min(_SCALE_MAX, scale))

    def _active_layer_id(self) -> str | None:
        """The active layer, which a Source of Active Layer follows (2.5)."""
        if self._source_mode is not BlurSourceMode.ACTIVE_LAYER:
            return None
        scene = self.scene()
        manager = getattr(scene, "layer_manager", None)
        active = manager.active_layer if manager is not None else None
        return active.layer_id if active is not None else None

    def _key(self, scale: float) -> tuple[Any, ...]:
        scene = self.scene()
        t = self.sceneTransform()
        area = self.effect_rect()
        return (
            (self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()),
            (area.x(), area.y(), area.width(), area.height()),
            self._blur_mode,
            self._region_shape,
            self._blur_radius,
            self._pixel_size,
            self._fill_color.rgba(),
            self._corner_radius,
            self._feather,
            self._invert_mask,
            None if self._alpha_mask is None else self._alpha_mask.cacheKey(),
            self._source_mode,
            self._source_layer_id,
            self._active_layer_id(),
            (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()),
            getattr(scene, "content_revision", 0),
            scale,
        )

    def rendered(self, scale: float = 1.0) -> tuple[QImage | None, QRectF]:
        """The effect image and the item rectangle it covers, from the cache when nothing
        it depends on has changed."""
        key = self._key(scale)
        if key != self._cache_key or self._cache_image is None:
            self._cache_image, self._cache_rect = self._render(scale)
            self._cache_key = key
        return self._cache_image, QRectF(self._cache_rect)

    def _render(self, scale: float) -> tuple[QImage | None, QRectF]:
        from snapmock.core.render_engine import RenderEngine

        scene = self.scene()
        area = self.effect_rect()
        if scene is None or area.isEmpty():
            return None, area
        w = max(1, math.ceil(area.width() * scale))
        h = max(1, math.ceil(area.height() * scale))
        if self._blur_mode is BlurMode.SOLID:
            effect = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            effect.fill(self._fill_color)
        else:
            gaussian = self._blur_mode is BlurMode.GAUSSIAN
            # The Gaussian works at half size and scales the result back (2.10), but only
            # where the radius already destroys the detail the halving would
            half = gaussian and self._blur_radius >= GAUSSIAN_HALF_SCALE_MIN_RADIUS
            capture_scale = scale * GAUSSIAN_RENDER_SCALE if half else scale
            # A Gaussian blur reads its neighbours: capture a margin and crop it away
            margin = self._blur_radius * 2.0 if gaussian else 0.0
            capture = area.adjusted(-margin, -margin, margin, margin)
            source = RenderEngine(scene).render_below(  # type: ignore[arg-type]
                self,
                capture,
                capture_scale,
                source_mode=self._source_mode.value,
                source_layer_id=self._source_layer_id,
            )
            if gaussian:
                blurred = blur_image(source, self._blur_radius * capture_scale)
                offset = round(margin * capture_scale)
                inner_w = max(1, math.ceil(area.width() * capture_scale))
                inner_h = max(1, math.ceil(area.height() * capture_scale))
                cropped = blurred.copy(QRect(offset, offset, inner_w, inner_h))
                effect = cropped.scaled(
                    w,
                    h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                effect = pixelate_image(source, round(self._pixel_size * scale))
        mask = self._mask_for(area, w, h)
        if self._feather > 0:
            mask = blur_image(mask, self._feather * scale / 2.0)
        painter = QPainter(effect)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, mask)
        painter.end()
        return effect, area

    def _mask_for(self, area: QRectF, w: int, h: int) -> QImage:
        """Where the effect shows, as an image *w* by *h* covering *area*: the region's
        shape, or a Freeform region's painted mask, and with Invert Mask the whole of
        *area* outside it (2.7)."""
        mask = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        mask.fill(Qt.GlobalColor.transparent)
        painter = QPainter(mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(w / area.width(), h / area.height())
        painter.translate(-area.topLeft())
        if self._invert_mask:
            painter.fillRect(area, QColor(255, 255, 255))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        freeform = self._region_shape is BlurRegionShape.FREEFORM
        if freeform and self._alpha_mask is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(self.region_rect(), self._alpha_mask)
        else:
            painter.fillPath(self.region_path(), QColor(255, 255, 255))
        painter.end()
        return mask

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        self._apply_flip(painter)
        if self._flip_horizontal or self._flip_vertical:
            # What lies beneath is never mirrored: undo the flip's mirror
            centre = self.boundingRect().center()
            painter.translate(centre)
            painter.scale(
                -1.0 if self._flip_horizontal else 1.0, -1.0 if self._flip_vertical else 1.0
            )
            painter.translate(-centre)
        image, target = self.rendered(self.render_scale(painter))
        if image is not None:
            painter.drawImage(target, image)
        if self._border_width > 0 and self._border_color.alpha() > 0:
            painter.setPen(QPen(self._border_color, self._border_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.region_path())
        self._end_flip(painter)

    # ------------------------------------------------------------ creation defaults

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        """Take the Blur tool's keys (2.6); a key the tool does not carry is left."""
        mode = defaults.get("blur_mode")
        if isinstance(mode, BlurMode):
            self._blur_mode = mode
        shape = defaults.get("region_shape")
        if isinstance(shape, BlurRegionShape):
            self._region_shape = shape
        if "blur_radius" in defaults:
            self._blur_radius = _clamp(
                defaults["blur_radius"], BLUR_RADIUS_MIN, BLUR_RADIUS_MAX, 10
            )
        if "pixel_size" in defaults:
            self._pixel_size = int(
                _clamp(defaults["pixel_size"], BLUR_PIXEL_SIZE_MIN, BLUR_PIXEL_SIZE_MAX, 10)
            )
        if "fill_color" in defaults:
            self._fill_color = QColor(defaults["fill_color"])
        if "corner_radius" in defaults:
            self._corner_radius = _clamp(defaults["corner_radius"], 0.0, CORNER_RADIUS_MAX, 0.0)
        if "feather" in defaults:
            self._feather = _clamp(defaults["feather"], 0.0, BLUR_FEATHER_MAX, 0.0)
        if "invert_mask" in defaults:
            self._invert_mask = bool(defaults["invert_mask"])
        source = defaults.get("source_mode")
        if isinstance(source, BlurSourceMode):
            self._source_mode = source
        if "opacity" in defaults:
            self.setOpacity(_clamp(defaults["opacity"], 0.0, 1.0, 1.0))
        self._changed()

    # ------------------------------------------------------------ serialization (5.1, 7.1)

    def mask_side_file(self) -> tuple[str, bytes] | None:
        """The archive entry and bytes a mask too large to inline needs, or None (7.1)."""
        value, png = encode_mask_field(self._alpha_mask, self.item_id)
        reference = mask_file_reference(value)
        if reference is None or not png:
            return None
        return reference, png

    def set_mask_png(self, data: bytes) -> None:
        """Take the mask the project serializer read from the archive (7.1)."""
        mask = decode_mask_png(data)
        if mask is not None:
            self._alpha_mask = mask
            self._changed()

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "BlurItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "transform": self._transform_entry(),
            "rect": [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()],
            "blur_mode": self._blur_mode.value,
            "region_shape": self._region_shape.value,
            "blur_radius": self._blur_radius,
            "pixel_size": self._pixel_size,
            "fill_color": self._fill_color.name(QColor.NameFormat.HexArgb),
            "corner_radius": self._corner_radius,
            "feather": self._feather,
            "invert_mask": self._invert_mask,
            "alpha_mask_data": encode_mask_field(self._alpha_mask, self.item_id)[0],
            "source_mode": self._source_mode.value,
            "source_layer_id": self._source_layer_id,
            "opacity": self.opacity(),
            "border_color": self._border_color.name(QColor.NameFormat.HexArgb),
            "border_width": self._border_width,
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> BlurItem:
        r = data.get("rect", [0, 0, 100, 100])
        if isinstance(r, dict):
            r = [r.get("x", 0), r.get("y", 0), r.get("w", 100), r.get("h", 100)]
        item = cls(rect=QRectF(r[0], r[1], r[2], r[3]), blur_radius=data.get("blur_radius", 10.0))
        pos = data.get("pos", [0, 0])
        item.setPos(pos[0], pos[1])
        item._apply_transform_entry(data)
        item.item_id = data.get("item_id", item.item_id)
        item.layer_id = data.get("layer_id", "")
        item._blur_mode = _enum_or(BlurMode, data.get("blur_mode"), BlurMode.GAUSSIAN)
        item._region_shape = _enum_or(
            BlurRegionShape, data.get("region_shape"), BlurRegionShape.RECTANGLE
        )
        item._pixel_size = int(
            _clamp(data.get("pixel_size", 10), BLUR_PIXEL_SIZE_MIN, BLUR_PIXEL_SIZE_MAX, 10)
        )
        item._fill_color = QColor(str(data.get("fill_color", DEFAULT_BLUR_FILL_COLOR)))
        item._corner_radius = _clamp(data.get("corner_radius", 0.0), 0.0, CORNER_RADIUS_MAX, 0.0)
        item._feather = _clamp(data.get("feather", 0.0), 0.0, BLUR_FEATHER_MAX, 0.0)
        item._invert_mask = bool(data.get("invert_mask", False))
        # A "file:" reference is resolved by the project serializer, which alone can read
        # the archive (7.1); it calls set_mask_png afterwards
        item._alpha_mask = decode_mask_field(data.get("alpha_mask_data"))
        item._source_mode = _enum_or(
            BlurSourceMode, data.get("source_mode"), BlurSourceMode.ALL_BELOW
        )
        raw_layer = data.get("source_layer_id")
        item._source_layer_id = str(raw_layer) if raw_layer else None
        item.setOpacity(_clamp(data.get("opacity", 1.0), 0.0, 1.0, 1.0))
        border = QColor(str(data.get("border_color", "#00000000")))
        item._border_color = border if border.isValid() else QColor(0, 0, 0, 0)
        item._border_width = _clamp(data.get("border_width", 0.0), 0.0, 50.0, 0.0)
        item._flip_horizontal = data.get("flip_horizontal", False)
        item._flip_vertical = data.get("flip_vertical", False)
        item._apply_blend_entry(data)
        return item
