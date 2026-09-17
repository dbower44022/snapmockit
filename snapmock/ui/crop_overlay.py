"""CropOverlay — visual overlay showing the crop region with handles and grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

from snapmock.core.theme_manager import current_theme
from snapmock.ui.transform_handles import HANDLE_HALF, HANDLE_SIZE

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene

# The resize cursor each handle shows, as the selection handles do (General UI PRD 6.6)
_CURSORS: dict[str, Qt.CursorShape] = {
    "top_left": Qt.CursorShape.SizeFDiagCursor,
    "top_center": Qt.CursorShape.SizeVerCursor,
    "top_right": Qt.CursorShape.SizeBDiagCursor,
    "middle_left": Qt.CursorShape.SizeHorCursor,
    "middle_right": Qt.CursorShape.SizeHorCursor,
    "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    "bottom_center": Qt.CursorShape.SizeVerCursor,
    "bottom_right": Qt.CursorShape.SizeFDiagCursor,
}


class CropHandleItem(QGraphicsRectItem):
    """Square resize handle for the crop region and the raster selection.

    Drawn as the selection handles are, a white square in the theme's handle colour at
    the same size, with the same resize cursor (end-to-end pass finding 13).
    """

    def __init__(self, position: str) -> None:
        super().__init__(-HANDLE_HALF, -HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE)
        self.position = position
        self.setPen(QPen(current_theme().selection_handle, 1))
        self.setBrush(QBrush(QColor(255, 255, 255)))
        self.setCursor(_CURSORS.get(position, Qt.CursorShape.ArrowCursor))
        self.setZValue(999999)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)


class CropOverlay(QGraphicsItemGroup):
    """Visual overlay for the crop tool showing dimmed area, border, grid, and handles."""

    def __init__(self, scene: SnapScene) -> None:
        super().__init__()
        self._scene_ref = scene
        self.setZValue(999990)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        # Dark overlay outside crop rect
        self._dim_path_item = QGraphicsPathItem()
        self._dim_path_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._dim_path_item.setBrush(QBrush(QColor(0, 0, 0, 128)))
        self._dim_path_item.setZValue(999990)
        self.addToGroup(self._dim_path_item)

        # Crop border
        self._border = QGraphicsRectItem()
        self._border.setPen(QPen(current_theme().accent, 2))
        self._border.setBrush(Qt.GlobalColor.transparent)
        self._border.setZValue(999991)
        self.addToGroup(self._border)

        # Rule-of-thirds grid (2 horizontal + 2 vertical lines as rects)
        self._grid_lines: list[QGraphicsRectItem] = []
        grid_pen = QPen(QColor(255, 255, 255, 77), 1)
        for _ in range(4):
            line = QGraphicsRectItem()
            line.setPen(grid_pen)
            line.setBrush(Qt.GlobalColor.transparent)
            line.setZValue(999992)
            self._grid_lines.append(line)
            self.addToGroup(line)

        # Dimensions label
        self._dims_label = QGraphicsSimpleTextItem()
        self._dims_label.setBrush(QBrush(QColor(255, 255, 255)))
        self._dims_label.setZValue(999993)
        self.addToGroup(self._dims_label)

        # 8 resize handles
        handle_positions = [
            "top_left",
            "top_center",
            "top_right",
            "middle_left",
            "middle_right",
            "bottom_left",
            "bottom_center",
            "bottom_right",
        ]
        self._handles: dict[str, CropHandleItem] = {}
        for pos in handle_positions:
            handle = CropHandleItem(pos)
            self._handles[pos] = handle
            self.addToGroup(handle)

        self._crop_rect = QRectF()
        self._show_grid = True

    @property
    def crop_rect(self) -> QRectF:
        return QRectF(self._crop_rect)

    def set_show_grid(self, show: bool) -> None:
        self._show_grid = show
        for line in self._grid_lines:
            line.setVisible(show)

    def update_crop_rect(self, rect: QRectF) -> None:
        """Update the crop rectangle and reposition all overlay elements."""
        self._crop_rect = QRectF(rect)
        canvas = self._scene_ref.canvas_rect

        # Dim overlay: full canvas minus crop rect
        path = QPainterPath()
        path.addRect(canvas)
        inner = QPainterPath()
        inner.addRect(rect)
        path = path.subtracted(inner)
        self._dim_path_item.setPath(path)

        # Border
        self._border.setRect(rect)

        # Grid lines (rule of thirds)
        w = rect.width()
        h = rect.height()
        if self._show_grid and w > 10 and h > 10:
            # Vertical lines at 1/3, 2/3
            self._grid_lines[0].setRect(rect.left() + w / 3, rect.top(), 0, h)
            self._grid_lines[1].setRect(rect.left() + 2 * w / 3, rect.top(), 0, h)
            # Horizontal lines at 1/3, 2/3
            self._grid_lines[2].setRect(rect.left(), rect.top() + h / 3, w, 0)
            self._grid_lines[3].setRect(rect.left(), rect.top() + 2 * h / 3, w, 0)
            for line in self._grid_lines:
                line.setVisible(True)
        else:
            for line in self._grid_lines:
                line.setVisible(False)

        # Dimensions label
        self._dims_label.setText(f"{int(w)} × {int(h)}")
        self._dims_label.setPos(rect.left() + 4, rect.top() - 20)

        # Handles
        cx = rect.center().x()
        cy = rect.center().y()
        positions = {
            "top_left": rect.topLeft(),
            "top_center": QPointF(cx, rect.top()),
            "top_right": rect.topRight(),
            "middle_left": QPointF(rect.left(), cy),
            "middle_right": QPointF(rect.right(), cy),
            "bottom_left": rect.bottomLeft(),
            "bottom_center": QPointF(cx, rect.bottom()),
            "bottom_right": rect.bottomRight(),
        }
        for pos_name, point in positions.items():
            self._handles[pos_name].setPos(point)

    def handle_at(self, scene_pos: QPointF) -> str | None:
        """Return which handle name (if any) is at *scene_pos*."""
        for name, handle in self._handles.items():
            hr = handle.sceneBoundingRect()
            hr.adjust(-3, -3, 3, 3)
            if hr.contains(scene_pos):
                return name
        return None

    def handle_cursor(self, name: str) -> QCursor:
        """The resize cursor of the handle called *name*."""
        return self._handles[name].cursor()

    def is_inside_crop(self, scene_pos: QPointF) -> bool:
        """Return True if *scene_pos* is inside the crop rectangle."""
        return self._crop_rect.contains(scene_pos)

    def add_to_scene(self) -> None:
        if self.scene() is None:
            self._scene_ref.addItem(self)

    def remove_from_scene(self) -> None:
        if self.scene() is not None:
            self._scene_ref.removeItem(self)
