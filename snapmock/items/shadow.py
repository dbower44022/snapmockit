"""Shadow helper — the five shadow properties and their painting, shared by every item
that has a shadow.

Numbered Steps, Stamps & Emoji PRD Sections 2.4, 3.5, and 4.4 give the numbered step, the
stamp, and the emoji a drop shadow; implementation decision 1 (option B) built it once
here and mixed it into those three items. The Vector Item Properties work mixes it into
``VectorItem`` (Basic Shape PRD 2.2) and the two text items (Text and Callout PRD 3.7,
4.8), each with its PRD's own defaults. The shadow is an offset, blurred copy of the
item's shape painted inside the item's own ``paint``, never a Qt graphics effect, so the
display, the raster exports, the layer thumbnails, and the clipboard agree. The blurred
copy is rendered into an image at the painter's current scale and cached until the shape,
the colour, the blur, or the scale changes.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from snapmock.config.constants import (
    DEFAULT_SHADOW_BLUR,
    DEFAULT_SHADOW_COLOR,
    DEFAULT_SHADOW_OFFSET,
)

SHADOW_KEYS: tuple[str, ...] = (
    "shadow_enabled",
    "shadow_color",
    "shadow_offset_x",
    "shadow_offset_y",
    "shadow_blur",
)
"""The five properties, in the order the PRD lists them; also the serialization keys."""

_MAX_SHADOW_IMAGE = 4096
"""Longest side of a cached shadow image, so a huge zoom does not allocate without bound."""


_DIRECT_BOX_MAX = 2
"""Up to this box radius a direct sum of shifted slices beats the cumulative sum.

Blur PRD 2.10, decision 4 (option C) of the Eyedropper and Blur performance work: a
cumulative sum costs the same whatever the box is, while a direct sum costs one add per
box pixel, so the two cross over between a box of two and a box of four. Measured on a
1004 by 1004 px capture, all four channels, the median of five runs: the direct sum takes
67 ms at a box of 1 and 86 ms at a box of 2, where the cumulative sum takes about 106 ms;
at a box of 4 the direct sum takes 134 ms and the cumulative sum 110 ms. A narrow box is
what a blur radius under 4 needs, which is where ``BlurItem``'s half-scale capture cannot
help, so this is what closes 2.10's 100 ms below that radius."""


def _box_pass(planes: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """One box blur of *radius* along *axis* over a float32 array of colour planes.

    Zero padding, as the shadow's blurred copy has always used: a shadow fades out at the
    edges of its own image, and a blur region's capture carries a margin that is cropped
    away.
    """
    if radius <= 0:
        return planes
    size = 2 * radius + 1
    if radius <= _DIRECT_BOX_MAX:
        total = np.zeros_like(planes)
        length = planes.shape[axis]
        for shift in range(-radius, radius + 1):
            # The window that lies inside the array; outside it the padding is zero, so
            # nothing is added. No padded copy is made: it would cost more than the sum.
            source = [slice(None)] * planes.ndim
            source[axis] = slice(max(0, shift), min(length, length + shift))
            target = [slice(None)] * planes.ndim
            target[axis] = slice(max(0, -shift), min(length, length - shift))
            np.add(total[tuple(target)], planes[tuple(source)], out=total[tuple(target)])
        total /= size
        return total
    pad = [(0, 0)] * planes.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(planes, pad, mode="constant")
    summed = np.cumsum(padded, axis=axis, dtype=np.float32)
    leading = list(summed.shape)
    leading[axis] = 1
    summed = np.concatenate([np.zeros(leading, dtype=np.float32), summed], axis=axis)
    upper = [slice(None)] * planes.ndim
    upper[axis] = slice(size, None)
    lower = [slice(None)] * planes.ndim
    lower[axis] = slice(None, -size)
    result: np.ndarray = (summed[tuple(upper)] - summed[tuple(lower)]) / size
    return result


def blur_image(image: QImage, radius: float) -> QImage:
    """*image* (ARGB32 premultiplied) blurred by three box passes, a close Gaussian.

    *radius* is in the image's pixels. A radius under half a pixel returns a copy.

    All four channels are blurred in one float32 array rather than one float64 plane at a
    time, and a narrow box uses a direct sum rather than a cumulative sum
    (:data:`_DIRECT_BOX_MAX`). Together they close Blur PRD 2.10's 100 ms for a 1000 by
    1000 px Gaussian region at every radius, on the main thread; the result is the same
    image the float64 form produced.
    """
    if radius < 0.5 or image.isNull():
        return image.copy()
    box = max(1, int(round(radius / 1.7)))
    width, height = image.width(), image.height()
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    pointer = image.bits()
    if pointer is None:
        return image.copy()
    pointer.setsize(image.sizeInBytes())
    stride = image.bytesPerLine()
    buffer = pointer.asstring(image.sizeInBytes())
    raw = np.frombuffer(buffer, dtype=np.uint8).reshape(height, stride)[:, : width * 4]
    pixels = raw.reshape(height, width, 4).astype(np.float32)
    for _pass in range(3):
        pixels = _box_pass(pixels, box, 0)
        pixels = _box_pass(pixels, box, 1)
    out = np.clip(np.rint(pixels), 0, 255).astype(np.uint8)
    result = QImage(
        out.tobytes(), width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied
    )
    return result.copy()


class ShadowMixin:
    """The shadow properties, their keys, and the painting.

    A class mixes this in ahead of its item base class and calls :meth:`_init_shadow`
    from ``__init__``. ``prepareGeometryChange`` and ``update`` are the item's.
    """

    _shadow_enabled: bool
    _shadow_color: QColor
    _shadow_offset_x: float
    _shadow_offset_y: float
    _shadow_blur: float
    _shadow_cache_key: tuple[Any, ...] | None
    _shadow_cache_path: QPainterPath | None
    _shadow_cache_image: QImage | None
    _shadow_cache_rect: QRectF

    def _init_shadow(
        self,
        enabled: bool = False,
        *,
        color: str = DEFAULT_SHADOW_COLOR,
        offset: float = DEFAULT_SHADOW_OFFSET,
        blur: float = DEFAULT_SHADOW_BLUR,
    ) -> None:
        """Set the shadow's defaults: the marker PRD's unless the item passes its own."""
        self._shadow_enabled = enabled
        self._shadow_color = QColor(color)
        self._shadow_offset_x = float(offset)
        self._shadow_offset_y = float(offset)
        self._shadow_blur = float(blur)
        self._shadow_cache_key = None
        self._shadow_cache_path = None
        self._shadow_cache_image = None
        self._shadow_cache_rect = QRectF()

    if TYPE_CHECKING:
        # The item's own methods, named for the type checker only: a real method here
        # would sit ahead of Qt's in the method resolution order and swallow the call.
        def prepareGeometryChange(self) -> None: ...  # noqa: N802
        def update(self, *args: Any) -> None: ...

    def _shadow_changed(self) -> None:
        self._shadow_cache_key = None
        self.prepareGeometryChange()
        self.update()

    @property
    def shadow_enabled(self) -> bool:
        return self._shadow_enabled

    @shadow_enabled.setter
    def shadow_enabled(self, value: bool) -> None:
        self._shadow_enabled = bool(value)
        self._shadow_changed()

    @property
    def shadow_color(self) -> QColor:
        return QColor(self._shadow_color)

    @shadow_color.setter
    def shadow_color(self, value: QColor) -> None:
        self._shadow_color = QColor(value)
        self._shadow_changed()

    @property
    def shadow_offset_x(self) -> float:
        return self._shadow_offset_x

    @shadow_offset_x.setter
    def shadow_offset_x(self, value: float) -> None:
        self._shadow_offset_x = float(value)
        self._shadow_changed()

    @property
    def shadow_offset_y(self) -> float:
        return self._shadow_offset_y

    @shadow_offset_y.setter
    def shadow_offset_y(self, value: float) -> None:
        self._shadow_offset_y = float(value)
        self._shadow_changed()

    @property
    def shadow_blur(self) -> float:
        return self._shadow_blur

    @shadow_blur.setter
    def shadow_blur(self, value: float) -> None:
        self._shadow_blur = max(0.0, float(value))
        self._shadow_changed()

    # --- geometry ---

    def shadow_rect(self, shape_rect: QRectF) -> QRectF:
        """The area the shadow of *shape_rect* covers; *shape_rect* itself when disabled."""
        if not self._shadow_enabled:
            return QRectF(shape_rect)
        spread = self._shadow_blur * 2.0
        return shape_rect.translated(self._shadow_offset_x, self._shadow_offset_y).adjusted(
            -spread, -spread, spread, spread
        )

    # --- painting ---

    def paint_shadow(self, painter: QPainter, path: QPainterPath) -> None:
        """Draw the shadow of *path* (item coordinates) if the shadow is enabled."""
        if not self._shadow_enabled or self._shadow_color.alpha() == 0 or path.isEmpty():
            return
        transform = painter.worldTransform()
        scale = math.sqrt(abs(transform.determinant())) or 1.0
        bounds = path.boundingRect()
        spread = self._shadow_blur * 2.0
        local_rect = bounds.adjusted(-spread, -spread, spread, spread)
        width = min(_MAX_SHADOW_IMAGE, max(1, math.ceil(local_rect.width() * scale)))
        height = min(_MAX_SHADOW_IMAGE, max(1, math.ceil(local_rect.height() * scale)))
        # The cache key holds the colour, the blur, and the scale; the path is kept and
        # compared natively, which is microseconds where a Python walk over the stroked
        # outline's elements was 7 ms a paint (end-to-end pass finding 8)
        key = (self._shadow_color.rgba(), round(self._shadow_blur, 3), round(scale, 3))
        cached_path = getattr(self, "_shadow_cache_path", None)
        if (
            key != self._shadow_cache_key
            or self._shadow_cache_image is None
            or cached_path is None
            or cached_path != path
        ):
            image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            image_painter = QPainter(image)
            image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            image_painter.scale(width / local_rect.width(), height / local_rect.height())
            image_painter.translate(-local_rect.topLeft())
            image_painter.fillPath(path, self._shadow_color)
            image_painter.end()
            self._shadow_cache_image = blur_image(image, self._shadow_blur * scale)
            self._shadow_cache_rect = QRectF(local_rect)
            self._shadow_cache_key = key
            self._shadow_cache_path = QPainterPath(path)
        target = self._shadow_cache_rect.translated(
            QPointF(self._shadow_offset_x, self._shadow_offset_y)
        )
        if getattr(self, "_item_blend_active", False):
            # The shadow does not take the item's blend mode (Blur PRD 3.7): normal
            # composition for the shadow, the item's mode restored for the content.
            mode = painter.compositionMode()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawImage(target, self._shadow_cache_image)
            painter.setCompositionMode(mode)
            return
        painter.drawImage(target, self._shadow_cache_image)

    # --- serialization ---

    def _shadow_data(self) -> dict[str, Any]:
        return {
            "shadow_enabled": self._shadow_enabled,
            "shadow_color": self._shadow_color.name(QColor.NameFormat.HexArgb),
            "shadow_offset_x": self._shadow_offset_x,
            "shadow_offset_y": self._shadow_offset_y,
            "shadow_blur": self._shadow_blur,
        }

    def _apply_shadow_data(self, data: dict[str, Any]) -> None:
        self._shadow_enabled = bool(data.get("shadow_enabled", self._shadow_enabled))
        if "shadow_color" in data:
            self._shadow_color = QColor(str(data["shadow_color"]))
        self._shadow_offset_x = float(data.get("shadow_offset_x", self._shadow_offset_x))
        self._shadow_offset_y = float(data.get("shadow_offset_y", self._shadow_offset_y))
        self._shadow_blur = max(0.0, float(data.get("shadow_blur", self._shadow_blur)))
        self._shadow_cache_key = None
