"""AddItemCommand — adds a SnapGraphicsItem to the scene."""

from __future__ import annotations

from typing import TYPE_CHECKING

from snapmock.core.command_stack import BaseCommand
from snapmock.items.base_item import SnapGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene


class AddItemCommand(BaseCommand):
    """Add an item to the scene and register it with the active layer."""

    def __init__(self, scene: SnapScene, item: SnapGraphicsItem, layer_id: str) -> None:
        self._scene = scene
        self._item = item
        self._layer_id = layer_id

    def redo(self) -> None:
        self._item.layer_id = self._layer_id
        self._scene.addItem(self._item)
        layer = self._scene.layer_manager.layer_by_id(self._layer_id)
        if layer is not None and self._item.item_id not in layer.item_ids:
            layer.item_ids.append(self._item.item_id)
        self._scene.last_added_item = self._item

    def undo(self) -> None:
        layer = self._scene.layer_manager.layer_by_id(self._layer_id)
        if layer is not None and self._item.item_id in layer.item_ids:
            layer.item_ids.remove(self._item.item_id)
        self._scene.removeItem(self._item)
        if self._scene.last_added_item is self._item:
            self._scene.last_added_item = None

    @property
    def description(self) -> str:
        return f"Add {self._item.type_name}"
