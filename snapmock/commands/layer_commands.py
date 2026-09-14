"""Layer commands — undoable layer add, remove, reorder, property change."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSizeF
from PyQt6.QtGui import QPixmap

from snapmock.core.command_stack import BaseCommand
from snapmock.core.layer import LAYER_TYPE_BACKGROUND, Layer
from snapmock.items.base_item import SnapGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.layer_manager import LayerManager
    from snapmock.core.scene import SnapScene
    from snapmock.items.raster_region_item import RasterRegionItem

BACKGROUND_LAYER_NAME = "Background"


class AddLayerCommand(BaseCommand):
    """Add a new layer and make it the active layer (General UI PRD 7.4; decided
    09-14-26 after a display run: the PRD says the layer goes above the active one and is
    silent on activation, and a user who presses Ctrl+Shift+N expects to draw on the layer
    just made). Undo removes it and puts the earlier active layer back."""

    def __init__(self, manager: LayerManager, name: str, index: int | None = None) -> None:
        self._mgr = manager
        self._name = name
        self._index = index
        self._layer: Layer | None = None
        self._previous_active_id: str = ""

    def redo(self) -> None:
        self._previous_active_id = self._mgr.active_layer_id
        if self._layer is None:
            self._layer = self._mgr.add_layer(self._name, self._index)
        else:
            self._mgr.insert_layer(self._layer, self._index or self._mgr.count)
        self._mgr.set_active(self._layer.layer_id)

    def undo(self) -> None:
        if self._layer is not None:
            self._mgr.remove_layer(self._layer.layer_id)
        if self._mgr.layer_by_id(self._previous_active_id) is not None:
            self._mgr.set_active(self._previous_active_id)

    @property
    def description(self) -> str:
        return f'Add layer "{self._name}"'


class DuplicateLayerCommand(BaseCommand):
    """Duplicate a layer and every item on it, above the original (General UI PRD 3.4)."""

    def __init__(self, scene: SnapScene, layer_id: str) -> None:
        self._scene = scene
        self._mgr = scene.layer_manager
        self._source_id = layer_id
        self._layer: Layer | None = None
        self._clones: list[SnapGraphicsItem] = []

    def redo(self) -> None:
        source = self._mgr.layer_by_id(self._source_id)
        if source is None:
            return
        if self._layer is None:
            self._layer = source.clone()
            self._layer.item_ids = []
            # Top-level items: a group's clone carries its members
            self._clones = [
                item.clone()
                for item in self._scene.annotation_items()
                if item.layer_id == self._source_id
            ]
        self._mgr.insert_layer(self._layer, self._mgr.index_of(self._source_id) + 1)
        for clone in self._clones:
            clone.layer_id = self._layer.layer_id
            self._scene.addItem(clone)
            if clone.item_id not in self._layer.item_ids:
                self._layer.item_ids.append(clone.item_id)
        self._mgr.set_active(self._layer.layer_id)

    def undo(self) -> None:
        if self._layer is None:
            return
        for clone in self._clones:
            if clone.scene() is self._scene:
                self._scene.removeItem(clone)
        self._layer.item_ids.clear()
        self._mgr.remove_layer(self._layer.layer_id)
        self._mgr.set_active(self._source_id)

    @property
    def description(self) -> str:
        return "Duplicate layer"


class RemoveLayerCommand(BaseCommand):
    """Remove a layer (undoable)."""

    def __init__(self, manager: LayerManager, layer_id: str) -> None:
        self._mgr = manager
        self._layer_id = layer_id
        self._layer: Layer | None = None
        self._index: int = -1

    def redo(self) -> None:
        self._index = self._mgr.index_of(self._layer_id)
        self._layer = self._mgr.remove_layer(self._layer_id)

    def undo(self) -> None:
        if self._layer is not None and self._index >= 0:
            self._mgr.insert_layer(self._layer, self._index)

    @property
    def description(self) -> str:
        return "Remove layer"


class ReorderLayerCommand(BaseCommand):
    """Move a layer to a new position in the stack."""

    def __init__(self, manager: LayerManager, layer_id: str, new_index: int) -> None:
        self._mgr = manager
        self._layer_id = layer_id
        self._new_index = new_index
        self._old_index: int = -1

    def redo(self) -> None:
        self._old_index = self._mgr.index_of(self._layer_id)
        self._mgr.move_layer(self._layer_id, self._new_index)

    def undo(self) -> None:
        self._mgr.move_layer(self._layer_id, self._old_index)

    @property
    def description(self) -> str:
        return "Reorder layers"


class ChangeLayerPropertyCommand(BaseCommand):
    """Change a layer property (visibility, lock, opacity, name, blend mode, layer type).

    With *mergeable* set, consecutive changes to the same property of the
    same layer collapse into one undo entry (the Layer Panel's opacity slider).
    """

    def __init__(
        self,
        manager: LayerManager,
        layer_id: str,
        prop_name: str,
        old_value: object,
        new_value: object,
        *,
        mergeable: bool = False,
    ) -> None:
        self._mgr = manager
        self._layer_id = layer_id
        self._prop_name = prop_name
        self._old_value = old_value
        self._new_value = new_value
        self._mergeable = mergeable

    @property
    def merge_id(self) -> int:
        if not self._mergeable:
            return 0
        return hash((self._layer_id, self._prop_name)) & 0x7FFFFFFF or 1

    def merge_with(self, other: BaseCommand) -> bool:
        if not isinstance(other, ChangeLayerPropertyCommand) or not other._mergeable:
            return False
        if other._layer_id != self._layer_id or other._prop_name != self._prop_name:
            return False
        self._new_value = other._new_value
        return True

    def _apply(self, value: object) -> None:
        if self._prop_name == "visible":
            self._mgr.set_visibility(self._layer_id, bool(value))
        elif self._prop_name == "locked":
            self._mgr.set_locked(self._layer_id, bool(value))
        elif self._prop_name == "opacity":
            self._mgr.set_opacity(self._layer_id, float(value))  # type: ignore[arg-type]
        elif self._prop_name == "name":
            self._mgr.rename_layer(self._layer_id, str(value))
        elif self._prop_name == "blend_mode":
            self._mgr.set_blend_mode(self._layer_id, str(value))
        elif self._prop_name == "layer_type":
            self._mgr.set_layer_type(self._layer_id, str(value))

    def redo(self) -> None:
        self._apply(self._new_value)

    def undo(self) -> None:
        self._apply(self._old_value)

    @property
    def description(self) -> str:
        return f"Change layer {self._prop_name}"


class CreateBackgroundLayerCommand(BaseCommand):
    """A Background layer holding *pixmap* at the bottom of the stack, the canvas resized
    to the image (General UI PRD 6.2: it fills the canvas exactly), as one undo step.

    The routes that place an image use it while the project has no Background layer and
    no annotation item (follow-up step 5): a dropped image file, a dropped image, a
    pasted system image, and File > Import Image. The active layer is left as it was,
    so the next annotation lands on an annotation layer.
    """

    def __init__(self, scene: SnapScene, pixmap: QPixmap) -> None:
        from snapmock.commands.raster_commands import ResizeCanvasCommand
        from snapmock.items.raster_region_item import RasterRegionItem

        self._scene = scene
        self._mgr = scene.layer_manager
        self._layer = Layer(name=BACKGROUND_LAYER_NAME, layer_type=LAYER_TYPE_BACKGROUND)
        self._item: RasterRegionItem = RasterRegionItem(pixmap=pixmap)
        self._item.setPos(0, 0)
        self._resize = ResizeCanvasCommand(
            scene, QSizeF(max(1, pixmap.width()), max(1, pixmap.height())), anchor=0
        )
        self._active_before = self._mgr.active_layer_id

    @property
    def layer(self) -> Layer:
        return self._layer

    @property
    def item(self) -> RasterRegionItem:
        return self._item

    def redo(self) -> None:
        self._mgr.insert_layer(self._layer, 0)
        self._item.layer_id = self._layer.layer_id
        self._scene.addItem(self._item)
        self._layer.item_ids = [self._item.item_id]
        self._item.setZValue(self._layer.z_base)
        self._resize.redo()
        if self._mgr.layer_by_id(self._active_before) is not None:
            self._mgr.set_active(self._active_before)

    def undo(self) -> None:
        self._resize.undo()
        self._layer.item_ids = []
        if self._item.scene() is self._scene:
            self._scene.removeItem(self._item)
        self._mgr.remove_layer(self._layer.layer_id)
        if self._mgr.layer_by_id(self._active_before) is not None:
            self._mgr.set_active(self._active_before)

    @property
    def description(self) -> str:
        return "Add background image"
