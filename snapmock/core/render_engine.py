"""RenderEngine — layer compositing for display and export.

Also the canvas border's painting (Navigation & Raster Operations PRD Section 10), which
the display and every export share so that what is on screen is what lands in the file.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene


_MAX_BORDER_SHADOW_IMAGE = 4096
"""Longest side of the border shadow's image, as the item shadow's own cap."""


# --- the canvas border (Navigation PRD 10.2, 10.4) -------------------------


def border_ring_path(scene: SnapScene) -> QPainterPath:
    """The ring between the canvas and the border's outer edge, in scene coordinates.

    Empty when there is no border. This is what the canvas background colour fills before
    the border stroke is painted over it (10.2), so a dashed or semi-transparent border
    shows the canvas colour through its gaps rather than the pasteboard.
    """
    path = QPainterPath()
    if not scene.has_border:
        return path
    outer = QPainterPath()
    outer.addRect(scene.border_rect)
    inner = QPainterPath()
    inner.addRect(scene.canvas_rect)
    return outer.subtracted(inner)


def paint_canvas_border(painter: QPainter, scene: SnapScene) -> None:
    """Paint the border's shadow, ring fill, and stroke in scene coordinates (10.4).

    A no-op when there is no border. The caller has already put *painter* into scene
    coordinates; nothing here reads the canvas size except through *scene*.
    """
    if not scene.has_border:
        return

    width = float(scene.border_width)
    outer = scene.border_rect

    shadow = scene.border_shadow
    if bool(shadow.get("shadow_enabled", False)):
        _paint_border_shadow(painter, outer, shadow)

    ring = border_ring_path(scene)
    background = scene.background_color
    if background.alpha() > 0:
        painter.fillPath(ring, background)

    color = scene.border_color
    if color.alpha() == 0:
        return
    from snapmock.items.vector_item import STROKE_STYLE_MAP

    pen = QPen(color, width, STROKE_STYLE_MAP.get(scene.border_style, Qt.PenStyle.SolidLine))
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.save()
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # The stroke's centre line sits half a width outside the canvas, so the stroke fills
    # the ring exactly and never covers the image (10.2).
    painter.drawRect(scene.canvas_rect.adjusted(-width / 2, -width / 2, width / 2, width / 2))
    painter.restore()


def _paint_border_shadow(painter: QPainter, outer: QRectF, shadow: dict[str, Any]) -> None:
    """Cast the border's drop shadow outward from *outer*, using the shared blur."""
    from snapmock.items.shadow import blur_image

    color = QColor(str(shadow.get("shadow_color", "#66000000")))
    if color.alpha() == 0:
        return
    blur = max(0.0, float(shadow.get("shadow_blur", 0.0)))
    offset_x = float(shadow.get("shadow_offset_x", 0.0))
    offset_y = float(shadow.get("shadow_offset_y", 0.0))
    spread = blur * 2.0
    local = outer.adjusted(-spread, -spread, spread, spread)
    transform = painter.worldTransform()
    scale = math.sqrt(abs(transform.determinant())) or 1.0
    width = min(_MAX_BORDER_SHADOW_IMAGE, max(1, math.ceil(local.width() * scale)))
    height = min(_MAX_BORDER_SHADOW_IMAGE, max(1, math.ceil(local.height() * scale)))
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    image_painter = QPainter(image)
    image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    image_painter.scale(width / local.width(), height / local.height())
    image_painter.translate(-local.topLeft())
    image_painter.fillRect(outer, color)
    image_painter.end()
    blurred = blur_image(image, blur * scale)
    painter.drawImage(local.translated(QPointF(offset_x, offset_y)), blurred)


class RenderEngine:
    """Composites visible layers into a final QImage for export.

    For on-screen rendering, QGraphicsView handles it directly.
    This class is for file export and raster pixel operations.
    """

    def __init__(self, scene: SnapScene) -> None:
        self._scene = scene

    def render_to_image(
        self,
        width: int | None = None,
        height: int | None = None,
        background: QColor | None = None,
    ) -> QImage:
        """Render the full scene to a QImage.

        If *width*/*height* are not specified, uses the scene's output rectangle: the
        canvas grown by the canvas border and its shadow (Navigation PRD 10.2). With no
        border that is the canvas size, so a document without one is unchanged.
        """
        source = self._scene.output_rect
        w = width if width is not None else int(round(source.width()))
        h = height if height is not None else int(round(source.height()))

        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        if background is not None:
            image.fill(background)
        else:
            image.fill(Qt.GlobalColor.white)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_border(painter, QRectF(0, 0, w, h), source)
        self._scene.render(painter, target=QRectF(0, 0, w, h), source=source)
        painter.end()
        return image

    def _paint_border(self, painter: QPainter, target: QRectF, source: QRectF) -> None:
        """Paint the canvas border into *target*, which shows *source* of the scene.

        A no-op without a border, and harmless when *source* lies inside the canvas: the
        border falls outside the clip and nothing is drawn.
        """
        if not self._scene.has_border or source.isEmpty():
            return
        painter.save()
        painter.setClipRect(target)
        painter.translate(target.topLeft())
        painter.scale(target.width() / source.width(), target.height() / source.height())
        painter.translate(-source.topLeft())
        paint_canvas_border(painter, self._scene)
        painter.restore()

    def render_region(
        self,
        rect: QRectF,
        background: QColor | None = None,
        scale: float = 1.0,
    ) -> QImage:
        """Render a specific rectangular region of the scene to a QImage.

        *scale* multiplies the output size: 2.0 renders *rect* at twice its
        scene dimensions (an export at 144 DPI when the scene is 72 DPI).
        """
        w = max(1, round(rect.width() * scale))
        h = max(1, round(rect.height() * scale))

        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        if background is not None:
            image.fill(background)
        else:
            image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_border(painter, QRectF(0, 0, w, h), rect)
        self._scene.render(
            painter,
            target=QRectF(0, 0, w, h),
            source=rect,
        )
        painter.end()
        return image

    def render_layers_composite(
        self,
        layer_ids: list[str],
        *,
        plain_layer_id: str | None = None,
        background: QColor | None = None,
    ) -> QImage:
        """The canvas-sized composite of the visible items on *layer_ids*, as displayed.

        Every other layer's items are hidden for the render; hidden layers among
        *layer_ids* contribute nothing, as on the display. Each item paints with its own
        layer's opacity and blend mode, except the items of *plain_layer_id*, which paint
        at full opacity in Normal mode: that layer keeps its own opacity and blend mode
        after a merge, so they must not be baked into its pixels (follow-up decision 1).
        *background* is painted first when given (Flatten All and the canvas colour).
        Top-level items only: a group's members ride with the group.
        """
        from snapmock.items.base_item import SnapGraphicsItem

        canvas = self._scene.canvas_size
        w = max(1, int(canvas.width()))
        h = max(1, int(canvas.height()))
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(background if background is not None else QColor(0, 0, 0, 0))

        wanted = set(layer_ids)
        hidden_items: list[SnapGraphicsItem] = []
        plain_items: list[tuple[SnapGraphicsItem, float, str]] = []
        for gitem in self._scene.annotation_items():
            if gitem.layer_id not in wanted:
                if gitem.isVisible():
                    gitem.setVisible(False)
                    hidden_items.append(gitem)
            elif gitem.layer_id == plain_layer_id:
                plain_items.append((gitem, gitem.layer_opacity, gitem.layer_blend_mode))
                gitem.layer_opacity = 1.0
                gitem.layer_blend_mode = "Normal"

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(
            painter,
            target=QRectF(0, 0, w, h),
            source=QRectF(0, 0, canvas.width(), canvas.height()),
        )
        painter.end()

        for gitem in hidden_items:
            gitem.setVisible(True)
        for gitem, opacity, mode in plain_items:
            gitem.layer_opacity = opacity
            gitem.layer_blend_mode = mode
        return image

    def source_layer_filter(
        self, source_mode: str | None, source_layer_id: str | None
    ) -> str | None:
        """The one layer a blur region's source mode reads, or None for every layer below
        (Blur PRD 2.5). ``active_layer`` follows the scene's active layer, so switching
        layers changes what such a region obscures; ``specific_layer`` falls back to every
        layer when the named layer is gone."""
        if source_mode == "active_layer":
            active = self._scene.layer_manager.active_layer
            return active.layer_id if active is not None else None
        if source_mode == "specific_layer":
            if source_layer_id and self._scene.layer_manager.layer_by_id(source_layer_id):
                return source_layer_id
            return None
        return None

    def render_below(
        self,
        target: QGraphicsItem,
        rect: QRectF,
        scale: float = 1.0,
        *,
        source_mode: str | None = None,
        source_layer_id: str | None = None,
    ) -> QImage:
        """What lies under *target* within *rect* (in *target*'s own coordinates, so a
        rotated region captures what it covers), *scale* times its size: the canvas colour,
        then every visible annotation item stacked below *target*, which is every item of
        the lower layers and the lower items of its own layer (Blur PRD 2.7; Basic Shape
        remainder silence 3).

        *source_mode* narrows that to one layer (2.5): ``active_layer`` reads the scene's
        active layer and ``specific_layer`` the layer *source_layer_id* names, each falling
        back to every layer below when there is no such layer. A narrowed capture leaves the
        canvas colour out, so a region over a layer that has nothing there obscures nothing.

        Each item is painted directly with its scene transform and effective opacity,
        nothing hidden or shown, so a paint can call this without painting *target* itself
        or scheduling another paint. A lower blur region paints its own result, so an
        upper region sees the lower one already blurred (the Performance section).
        """
        from PyQt6.QtWidgets import QStyleOptionGraphicsItem

        from snapmock.items.base_item import SnapGraphicsItem

        w = max(1, math.ceil(rect.width() * scale))
        h = max(1, math.ceil(rect.height() * scale))
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(w / max(rect.width(), 1e-9), h / max(rect.height(), 1e-9))
        painter.translate(-rect.topLeft())
        to_local, invertible = target.sceneTransform().inverted()
        if invertible:
            painter.setTransform(to_local, True)
        scene_rect = target.mapRectToScene(rect)
        only_layer = self.source_layer_filter(source_mode, source_layer_id)
        narrowed = source_mode in ("active_layer", "specific_layer")
        canvas = self._scene.canvas_rect.intersected(scene_rect)
        background = self._scene.background_color
        if not narrowed and background.alpha() > 0 and not canvas.isEmpty():
            painter.fillRect(canvas, background)
        option = QStyleOptionGraphicsItem()
        for gitem in self._scene.items(Qt.SortOrder.AscendingOrder):
            if gitem is target:
                break
            if not isinstance(gitem, SnapGraphicsItem) or not gitem.isVisible():
                continue
            if only_layer is not None and gitem.layer_id != only_layer:
                continue
            if target.isAncestorOf(gitem) or not gitem.sceneBoundingRect().intersects(scene_rect):
                continue
            painter.save()
            painter.setTransform(gitem.sceneTransform(), True)
            painter.setOpacity(gitem.effectiveOpacity())
            gitem.paint(painter, option, None)
            painter.restore()
        painter.end()
        return image

    def render_sample(self, rect: QRectF) -> QImage:
        """What the Eyedropper reads over *rect*, in scene coordinates at canvas scale
        (Blur PRD 4.2): the canvas colour where the canvas covers *rect*, then every
        visible annotation item in stacking order, exactly as the display composites them.

        Only :class:`SnapGraphicsItem` instances are painted, so the grid, the guides, the
        crosshairs, the marching ants of a raster selection, the crop overlay's dimming and
        handles, and the pasteboard are all left out, and so is the preview loupe, which is
        a widget (Eyedropper and Blur performance decisions 1 and 2). The render is clipped
        to the canvas, so a sample over the pasteboard beyond the canvas edge is transparent
        whatever hangs over it there (4.3, 8.3).
        """
        from PyQt6.QtWidgets import QStyleOptionGraphicsItem

        from snapmock.items.base_item import SnapGraphicsItem

        w = max(1, math.ceil(rect.width()))
        h = max(1, math.ceil(rect.height()))
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        canvas = self._scene.canvas_rect.intersected(rect)
        if canvas.isEmpty():
            return image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-rect.topLeft())
        painter.setClipRect(canvas)
        background = self._scene.background_color
        if background.alpha() > 0:
            painter.fillRect(canvas, background)
        option = QStyleOptionGraphicsItem()
        for gitem in self._scene.items(Qt.SortOrder.AscendingOrder):
            if not isinstance(gitem, SnapGraphicsItem) or not gitem.isVisible():
                continue
            if not gitem.sceneBoundingRect().intersects(rect):
                continue
            painter.save()
            painter.setTransform(gitem.sceneTransform(), True)
            painter.setOpacity(gitem.effectiveOpacity())
            gitem.paint(painter, option, None)
            painter.restore()
        painter.end()
        return image

    def render_layer_region(
        self,
        layer_id: str,
        rect: QRectF,
        scale: float = 1.0,
    ) -> QImage:
        """Render only items on *layer_id* within *rect* to a QImage.

        *scale* multiplies the output size, as in :meth:`render_region`. Items
        on the layer are drawn even when the layer is hidden, so a Layer Panel
        thumbnail shows what the layer holds.
        """
        from snapmock.items.base_item import SnapGraphicsItem

        w = max(1, round(rect.width() * scale))
        h = max(1, round(rect.height() * scale))

        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)

        # Temporarily hide items not on the target layer, and show the target's.
        # Top-level items only: a group's members follow the group, and toggling a
        # member's own flag would leave it hidden inside a group shown again later.
        hidden_items: list[SnapGraphicsItem] = []
        shown_items: list[SnapGraphicsItem] = []
        for gitem in self._scene.annotation_items():
            if gitem.layer_id != layer_id:
                if gitem.isVisible():
                    gitem.setVisible(False)
                    hidden_items.append(gitem)
            elif not gitem.isVisible():
                gitem.setVisible(True)
                shown_items.append(gitem)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(
            painter,
            target=QRectF(0, 0, w, h),
            source=rect,
        )
        painter.end()

        # Restore visibility
        for gitem in hidden_items:
            gitem.setVisible(True)
        for gitem in shown_items:
            gitem.setVisible(False)

        return image
