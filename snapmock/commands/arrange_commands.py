"""Arrange commands — z-order, alignment, and distribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF

from snapmock.core.command_stack import BaseCommand
from snapmock.items.base_item import SnapGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene


def apply_layer_z_values(scene: SnapScene, layer_id: str) -> None:
    """Give every top-level item on *layer_id* the z-value of its place in ``item_ids``.

    A group's members are its child items and stack among themselves inside the group,
    so only the top-level items are walked.
    """
    layer = scene.layer_manager.layer_by_id(layer_id)
    if layer is None:
        return
    by_id = {item.item_id: item for item in scene.annotation_items()}
    for index, item_id in enumerate(layer.item_ids):
        item = by_id.get(item_id)
        if item is not None:
            item.setZValue(layer.z_base + index)


class ChangeZOrderCommand(BaseCommand):
    """Change z-order of items within their layer.

    Parameters
    ----------
    scene : SnapScene
    items : list of SnapGraphicsItem
    mode : str
        One of "front", "forward", "backward", "back".
    """

    def __init__(self, scene: SnapScene, items: list[SnapGraphicsItem], mode: str) -> None:
        self._scene = scene
        self._items = list(items)
        self._mode = mode
        # Save old item_ids ordering per affected layer
        self._old_orders: dict[str, list[str]] = {}

    def redo(self) -> None:
        # Group items by layer
        layers_affected: dict[str, list[SnapGraphicsItem]] = {}
        for item in self._items:
            layers_affected.setdefault(item.layer_id, []).append(item)

        lm = self._scene.layer_manager
        for layer_id, items in layers_affected.items():
            layer = lm.layer_by_id(layer_id)
            if layer is None:
                continue
            # Save old order for undo
            self._old_orders[layer_id] = list(layer.item_ids)
            item_id_set = {i.item_id for i in items}

            if self._mode == "front":
                # Move to end (top) of list
                rest = [iid for iid in layer.item_ids if iid not in item_id_set]
                moved = [iid for iid in layer.item_ids if iid in item_id_set]
                layer.item_ids[:] = rest + moved
            elif self._mode == "back":
                # Move to beginning (bottom) of list
                moved = [iid for iid in layer.item_ids if iid in item_id_set]
                rest = [iid for iid in layer.item_ids if iid not in item_id_set]
                layer.item_ids[:] = moved + rest
            elif self._mode == "forward":
                # Move each item one step toward end
                ids = list(layer.item_ids)
                for i in range(len(ids) - 2, -1, -1):
                    if ids[i] in item_id_set and ids[i + 1] not in item_id_set:
                        ids[i], ids[i + 1] = ids[i + 1], ids[i]
                layer.item_ids[:] = ids
            elif self._mode == "backward":
                # Move each item one step toward beginning
                ids = list(layer.item_ids)
                for i in range(1, len(ids)):
                    if ids[i] in item_id_set and ids[i - 1] not in item_id_set:
                        ids[i], ids[i - 1] = ids[i - 1], ids[i]
                layer.item_ids[:] = ids

            self._apply_z_values(layer_id)

    def undo(self) -> None:
        lm = self._scene.layer_manager
        for layer_id, old_ids in self._old_orders.items():
            layer = lm.layer_by_id(layer_id)
            if layer is not None:
                layer.item_ids[:] = old_ids
                self._apply_z_values(layer_id)

    def _apply_z_values(self, layer_id: str) -> None:
        apply_layer_z_values(self._scene, layer_id)

    @property
    def description(self) -> str:
        mode_labels = {
            "front": "Bring to Front",
            "forward": "Bring Forward",
            "backward": "Send Backward",
            "back": "Send to Back",
        }
        return mode_labels.get(self._mode, "Change Z-Order")


class AlignItemsCommand(BaseCommand):
    """Align items to a common edge or center.

    Parameters
    ----------
    items : list of SnapGraphicsItem
    alignment : str
        One of "left", "center_h", "right", "top", "middle_v", "bottom".
    """

    def __init__(
        self,
        items: list[SnapGraphicsItem],
        alignment: str,
        *,
        movable: list[SnapGraphicsItem] | None = None,
    ) -> None:
        self._items = list(items)
        self._alignment = alignment
        # The items that move; the others (locked ones, the item lock of 09-25-26) still
        # count towards the edge or centre aligned to
        self._movable = list(items) if movable is None else list(movable)
        self._old_positions: list[QPointF] = []

    def redo(self) -> None:
        self._old_positions = [QPointF(item.pos()) for item in self._movable]
        if len(self._items) < 2:
            return

        rects = [item.sceneBoundingRect() for item in self._items]

        if self._alignment == "left":
            ref = min(r.left() for r in rects)
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x() + ref - rect.left(), item.pos().y())
        elif self._alignment == "center_h":
            union_left = min(r.left() for r in rects)
            union_right = max(r.right() for r in rects)
            center_x = (union_left + union_right) / 2
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x() + center_x - rect.center().x(), item.pos().y())
        elif self._alignment == "right":
            ref = max(r.right() for r in rects)
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x() + ref - rect.right(), item.pos().y())
        elif self._alignment == "top":
            ref = min(r.top() for r in rects)
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x(), item.pos().y() + ref - rect.top())
        elif self._alignment == "middle_v":
            union_top = min(r.top() for r in rects)
            union_bottom = max(r.bottom() for r in rects)
            center_y = (union_top + union_bottom) / 2
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x(), item.pos().y() + center_y - rect.center().y())
        elif self._alignment == "bottom":
            ref = max(r.bottom() for r in rects)
            for item, rect in self._moving(rects):
                item.setPos(item.pos().x(), item.pos().y() + ref - rect.bottom())

    def _moving(self, rects: list[QRectF]) -> list[tuple[SnapGraphicsItem, QRectF]]:
        return [(i, r) for i, r in zip(self._items, rects) if i in self._movable]

    def undo(self) -> None:
        for item, pos in zip(self._movable, self._old_positions):
            item.setPos(pos)

    @property
    def description(self) -> str:
        labels = {
            "left": "Align Left",
            "center_h": "Align Center Horizontal",
            "right": "Align Right",
            "top": "Align Top",
            "middle_v": "Align Middle Vertical",
            "bottom": "Align Bottom",
        }
        return labels.get(self._alignment, "Align Items")


class DistributeItemsCommand(BaseCommand):
    """Distribute items evenly along an axis.

    Parameters
    ----------
    items : list of SnapGraphicsItem
    direction : str
        "horizontal" or "vertical".
    """

    def __init__(self, items: list[SnapGraphicsItem], direction: str) -> None:
        self._items = list(items)
        self._direction = direction
        self._old_positions: list[QPointF] = []

    def redo(self) -> None:
        self._old_positions = [QPointF(item.pos()) for item in self._items]
        if len(self._items) < 3:
            return

        rects = [item.sceneBoundingRect() for item in self._items]

        if self._direction == "horizontal":
            # Sort by left edge
            pairs = sorted(zip(self._items, rects), key=lambda p: p[1].left())
            total_width = sum(r.width() for _, r in pairs)
            union_left = pairs[0][1].left()
            union_right = pairs[-1][1].right()
            gap = (union_right - union_left - total_width) / (len(pairs) - 1)
            x = union_left
            for item, rect in pairs:
                item.setPos(item.pos().x() + x - rect.left(), item.pos().y())
                x += rect.width() + gap
        elif self._direction == "vertical":
            # Sort by top edge
            pairs = sorted(zip(self._items, rects), key=lambda p: p[1].top())
            total_height = sum(r.height() for _, r in pairs)
            union_top = pairs[0][1].top()
            union_bottom = pairs[-1][1].bottom()
            gap = (union_bottom - union_top - total_height) / (len(pairs) - 1)
            y = union_top
            for item, rect in pairs:
                item.setPos(item.pos().x(), item.pos().y() + y - rect.top())
                y += rect.height() + gap

    def undo(self) -> None:
        for item, pos in zip(self._items, self._old_positions):
            item.setPos(pos)

    @property
    def description(self) -> str:
        if self._direction == "horizontal":
            return "Distribute Horizontally"
        return "Distribute Vertically"


class AlignToCanvasCommand(BaseCommand):
    """Center items on the canvas.

    Parameters
    ----------
    scene : SnapScene
    items : list of SnapGraphicsItem
    """

    def __init__(self, scene: SnapScene, items: list[SnapGraphicsItem]) -> None:
        self._scene = scene
        self._items = list(items)
        self._old_positions: list[QPointF] = []

    def redo(self) -> None:
        self._old_positions = [QPointF(item.pos()) for item in self._items]
        if not self._items:
            return

        canvas = self._scene.canvas_size
        canvas_cx = canvas.width() / 2
        canvas_cy = canvas.height() / 2

        # Compute bounding union of all items
        union = self._items[0].sceneBoundingRect()
        for item in self._items[1:]:
            union = union.united(item.sceneBoundingRect())

        dx = canvas_cx - union.center().x()
        dy = canvas_cy - union.center().y()

        for item in self._items:
            item.setPos(item.pos().x() + dx, item.pos().y() + dy)

    def undo(self) -> None:
        for item, pos in zip(self._items, self._old_positions):
            item.setPos(pos)

    @property
    def description(self) -> str:
        return "Align to Canvas Center"
