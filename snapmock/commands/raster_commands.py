"""Raster commands — CropCanvas, RasterCut, ResizeCanvas, ResizeImage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF, QSizeF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap

from snapmock.core.command_stack import BaseCommand
from snapmock.items.base_item import SnapGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.items.raster_region_item import RasterRegionItem


class CropCanvasCommand(BaseCommand):
    """Crop the canvas to a specified rectangle, repositioning items."""

    def __init__(self, scene: SnapScene, crop_rect: QRectF) -> None:
        self._scene = scene
        self._crop_rect = QRectF(crop_rect)
        self._old_size = QSizeF(scene.canvas_size)
        self._offset = QPointF(crop_rect.topLeft())
        # Store original item positions for undo
        # Top-level items only: a group's members ride with the group
        self._item_positions: list[tuple[SnapGraphicsItem, QPointF]] = [
            (gitem, QPointF(gitem.pos())) for gitem in scene.annotation_items()
        ]
        # Track items removed because they were entirely outside the crop
        self._removed_items: list[tuple[SnapGraphicsItem, str]] = []
        # Images cut at the new edge, with the pixels they had (Navigation PRD 7.6)
        self._clipped: list[tuple[RasterRegionItem, QPixmap]] = []

    def redo(self) -> None:
        # Translate all items by -offset
        for gitem, _orig_pos in self._item_positions:
            gitem.setPos(gitem.pos() - self._offset)

        # Remove items entirely outside the new canvas bounds
        new_rect = QRectF(0, 0, self._crop_rect.width(), self._crop_rect.height())
        self._removed_items.clear()
        for gitem, _orig_pos in self._item_positions:
            item_rect = gitem.sceneBoundingRect()
            if not new_rect.intersects(item_rect):
                self._removed_items.append((gitem, gitem.layer_id))
                self._scene.removeItem(gitem)

        self._clip_images(new_rect)
        self._scene.set_canvas_size(self._crop_rect.size())

    def _clip_images(self, canvas: QRectF) -> None:
        """Cut every image that crosses the new edge to the canvas (Navigation PRD 7.6;
        end-to-end pass finding 14). An image that is rotated, scaled, or flipped keeps
        its pixels, since its pixels do not map to the canvas one to one."""
        from snapmock.items.raster_region_item import RasterRegionItem

        self._clipped.clear()
        for gitem, _orig_pos in self._item_positions:
            if not isinstance(gitem, RasterRegionItem) or gitem.scene() is None:
                continue
            if (
                not gitem.transform().isIdentity()
                or gitem.rotation() != 0
                or gitem.scale() != 1
                or gitem.flip_horizontal
                or gitem.flip_vertical
            ):
                continue
            bounds = gitem.sceneBoundingRect()
            kept = bounds.intersected(canvas)
            if kept == bounds or kept.isEmpty():
                continue
            original = gitem.pixmap
            local = kept.translated(-gitem.pos()).toAlignedRect()
            self._clipped.append((gitem, original))
            gitem.pixmap = original.copy(local)
            gitem.setPos(gitem.pos() + QPointF(local.topLeft()))

    def undo(self) -> None:
        self._scene.set_canvas_size(self._old_size)

        # Give the cut images their pixels back; the positions follow below
        for image, pixmap in self._clipped:
            image.pixmap = pixmap
        self._clipped.clear()

        # Re-add removed items
        for gitem, layer_id in self._removed_items:
            gitem.layer_id = layer_id
            self._scene.addItem(gitem)
        self._removed_items.clear()

        # Restore original positions
        for gitem, orig_pos in self._item_positions:
            gitem.setPos(orig_pos)

    @property
    def description(self) -> str:
        return "Crop canvas"


class RasterCutCommand(BaseCommand):
    """Cut (erase) pixels from a raster selection region."""

    def __init__(
        self,
        scene: SnapScene,
        selection_rect: QRectF,
        original_pixels: QImage,
        source_layer_id: str,
    ) -> None:
        self._scene = scene
        self._selection_rect = QRectF(selection_rect)
        self._original_pixels = QImage(original_pixels)
        self._source_layer_id = source_layer_id
        # Backup of (item, original_pixmap) for affected RasterRegionItems
        self._backups: list[tuple[RasterRegionItem, QPixmap]] = []

    def redo(self) -> None:
        from snapmock.items.raster_region_item import RasterRegionItem

        self._backups.clear()
        for gitem in self._scene.items():
            if not isinstance(gitem, RasterRegionItem):
                continue
            if gitem.layer_id != self._source_layer_id:
                continue
            item_rect = gitem.sceneBoundingRect()
            if not self._selection_rect.intersects(item_rect):
                continue
            # Save original pixmap for undo
            self._backups.append((gitem, QPixmap(gitem._pixmap)))  # noqa: SLF001
            # Erase the intersection region using QImage (QPixmap lacks alpha on X11)
            local_rect = gitem.mapRectFromScene(self._selection_rect)
            img = gitem._pixmap.toImage().convertToFormat(  # noqa: SLF001
                QImage.Format.Format_ARGB32_Premultiplied
            )
            painter = QPainter(img)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(local_rect, QColor(0, 0, 0, 0))
            painter.end()
            gitem.prepareGeometryChange()
            gitem._pixmap = QPixmap.fromImage(img)  # noqa: SLF001
            gitem.update()

    def undo(self) -> None:
        for gitem, original_pixmap in self._backups:
            gitem.prepareGeometryChange()
            gitem._pixmap = QPixmap(original_pixmap)  # noqa: SLF001
            gitem.update()
        self._backups.clear()

    @property
    def description(self) -> str:
        return "Raster cut"


class ResizeCanvasCommand(BaseCommand):
    """Resize the canvas, repositioning items based on an anchor point."""

    # Anchor grid: 0=top-left, 1=top-center, 2=top-right, etc.
    def __init__(
        self,
        scene: SnapScene,
        new_size: QSizeF,
        anchor: int = 4,  # center
        fill_color: QColor | None = None,
    ) -> None:
        self._scene = scene
        self._new_size = QSizeF(new_size)
        self._old_size = QSizeF(scene.canvas_size)
        self._anchor = anchor
        self._fill_color = fill_color or QColor("white")
        # Top-level items only: a group's members ride with the group
        self._item_offsets: list[tuple[SnapGraphicsItem, QPointF]] = [
            (gitem, QPointF(gitem.pos())) for gitem in scene.annotation_items()
        ]
        self._offset = self._compute_offset()

    def _compute_offset(self) -> QPointF:
        dw = self._new_size.width() - self._old_size.width()
        dh = self._new_size.height() - self._old_size.height()
        row = self._anchor // 3
        col = self._anchor % 3
        ox = dw * col / 2.0
        oy = dh * row / 2.0
        return QPointF(ox, oy)

    def redo(self) -> None:
        for gitem, _orig in self._item_offsets:
            gitem.setPos(gitem.pos() + self._offset)
        self._scene.set_canvas_size(self._new_size)

    def undo(self) -> None:
        self._scene.set_canvas_size(self._old_size)
        for gitem, orig in self._item_offsets:
            gitem.setPos(orig)

    @property
    def description(self) -> str:
        return "Resize canvas"


class ResizeImageCommand(BaseCommand):
    """Scale all items and the canvas to a new size."""

    def __init__(
        self,
        scene: SnapScene,
        new_size: QSizeF,
    ) -> None:
        self._scene = scene
        self._new_size = QSizeF(new_size)
        self._old_size = QSizeF(scene.canvas_size)
        # Store serialized item state for undo (captures all geometry)
        # Top-level items only: a group scales its members and their offsets itself
        self._item_snapshots: list[tuple[SnapGraphicsItem, QPointF, dict[str, Any]]] = [
            (gitem, QPointF(gitem.pos()), gitem.serialize()) for gitem in scene.annotation_items()
        ]

    def redo(self) -> None:
        sx = self._new_size.width() / max(self._old_size.width(), 1)
        sy = self._new_size.height() / max(self._old_size.height(), 1)
        for gitem, orig_pos, _snapshot in self._item_snapshots:
            gitem.setPos(orig_pos.x() * sx, orig_pos.y() * sy)
            gitem.scale_geometry(sx, sy)
        self._scene.set_canvas_size(self._new_size)

    def undo(self) -> None:
        self._scene.set_canvas_size(self._old_size)
        from snapmock.io.project_serializer import ITEM_REGISTRY

        for gitem, orig_pos, snapshot in self._item_snapshots:
            gitem.setPos(orig_pos)
            # Restore geometry from snapshot
            item_type = snapshot.get("type", "")
            cls = ITEM_REGISTRY.get(item_type)
            if cls is not None:
                restored = cls.deserialize(snapshot)
                # Copy geometry from restored to existing item via serialize/apply
                self._restore_geometry(gitem, restored)

    @staticmethod
    def _restore_geometry(target: SnapGraphicsItem, source: SnapGraphicsItem) -> None:
        """Copy internal geometry from source back to target."""
        from snapmock.items.arc_item import ArcItem
        from snapmock.items.arrow_item import ArrowItem
        from snapmock.items.blur_item import BlurItem
        from snapmock.items.callout_item import CalloutItem
        from snapmock.items.ellipse_item import EllipseItem
        from snapmock.items.freehand_item import FreehandItem
        from snapmock.items.group_item import GroupItem
        from snapmock.items.highlight_item import HighlightItem
        from snapmock.items.line_item import LineItem
        from snapmock.items.numbered_step_item import NumberedStepItem
        from snapmock.items.polygon_item import PolygonItem
        from snapmock.items.raster_region_item import RasterRegionItem
        from snapmock.items.rectangle_item import RectangleItem
        from snapmock.items.stamp_item import StampItem
        from snapmock.items.text_item import TextItem
        from snapmock.items.vector_item import VectorItem

        target.prepareGeometryChange()

        if isinstance(target, GroupItem) and isinstance(source, GroupItem):
            # A group's snapshot carries its members: restore each member from its own
            # entry, position included, since the group scaled their offsets too.
            for member, restored in zip(target.members, source.members):
                member.setPos(restored.pos())
                ResizeImageCommand._restore_geometry(member, restored)
            return

        # Restore stroke properties for vector items
        if isinstance(target, VectorItem) and isinstance(source, VectorItem):
            target._stroke_width = source._stroke_width  # noqa: SLF001
            target._stroke_color = source._stroke_color  # noqa: SLF001
            target._fill_color = source._fill_color  # noqa: SLF001

        if isinstance(target, RectangleItem) and isinstance(source, RectangleItem):
            target._rect = source._rect  # noqa: SLF001
            target._corner_radius = source._corner_radius  # noqa: SLF001
            target._corners = dict(source._corners)  # noqa: SLF001
        elif isinstance(target, EllipseItem) and isinstance(source, EllipseItem):
            target._rect = source._rect  # noqa: SLF001
        elif isinstance(target, (LineItem, ArrowItem)) and isinstance(
            source, (LineItem, ArrowItem)
        ):
            target._line = source._line  # noqa: SLF001
        elif isinstance(target, ArcItem) and isinstance(source, ArcItem):
            target._start = source._start  # noqa: SLF001
            target._end = source._end  # noqa: SLF001
            target._control = source._control  # noqa: SLF001
        elif isinstance(target, PolygonItem) and isinstance(source, PolygonItem):
            target._vertices = source._vertices  # noqa: SLF001
            target._center = source._center  # noqa: SLF001
            target._radius = source._radius  # noqa: SLF001
        elif isinstance(target, FreehandItem) and isinstance(source, FreehandItem):
            target._path_points = source._path_points  # noqa: SLF001
            target._segments = source._segments  # noqa: SLF001
            target._preview = source._preview  # noqa: SLF001
            target._path = source._path  # noqa: SLF001
        elif isinstance(target, HighlightItem) and isinstance(source, HighlightItem):
            target._points = source._points  # noqa: SLF001
            target._path = source._path  # noqa: SLF001
        elif isinstance(target, TextItem) and isinstance(source, TextItem):
            target.font = source.font
            target._width = source._width  # noqa: SLF001
        elif isinstance(target, CalloutItem) and isinstance(source, CalloutItem):
            target._rect = source._rect  # noqa: SLF001
            target._tail_tip = source._tail_tip  # noqa: SLF001
            target.font = source.font
        elif isinstance(target, BlurItem) and isinstance(source, BlurItem):
            target._rect = source._rect  # noqa: SLF001
            target._blur_radius = source._blur_radius  # noqa: SLF001
            target._corner_radius = source._corner_radius  # noqa: SLF001
            target._feather = source._feather  # noqa: SLF001
            target._alpha_mask = source._alpha_mask  # noqa: SLF001
            target._cache_key = None  # noqa: SLF001
        elif isinstance(target, RasterRegionItem) and isinstance(source, RasterRegionItem):
            target._pixmap = source._pixmap  # noqa: SLF001
        elif isinstance(target, NumberedStepItem) and isinstance(source, NumberedStepItem):
            target._badge_size = source._badge_size  # noqa: SLF001
            target._font_size = source._font_size  # noqa: SLF001
            target._label_font_size = source._label_font_size  # noqa: SLF001
        elif isinstance(target, StampItem) and isinstance(source, StampItem):
            target._stamp_size = source._stamp_size  # noqa: SLF001
            target._stretch = source._stretch  # noqa: SLF001

        target.update()

    @property
    def description(self) -> str:
        return "Resize image"
