"""SnapScene — the backbone QGraphicsScene that owns LayerManager + CommandStack."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, QSizeF, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from snapmock.config.constants import (
    DEFAULT_CANVAS_DPI,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    PASTEBOARD_MARGIN,
)
from snapmock.core.command_stack import CommandStack
from snapmock.core.guides import Guide
from snapmock.core.layer_manager import LayerManager

if TYPE_CHECKING:
    from snapmock.items.base_item import SnapGraphicsItem


class SnapScene(QGraphicsScene):
    """Extended QGraphicsScene with layer and command-stack management.

    Signals
    -------
    canvas_size_changed(QSizeF)
        Emitted when the logical canvas size changes.
    guides_changed()
        Emitted after the guide list changes (General UI PRD 6.5).
    """

    canvas_size_changed = pyqtSignal(QSizeF)
    background_changed = pyqtSignal()
    canvas_dpi_changed = pyqtSignal(int)
    guides_changed = pyqtSignal()

    def __init__(
        self,
        width: int = DEFAULT_CANVAS_WIDTH,
        height: int = DEFAULT_CANVAS_HEIGHT,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._canvas_size = QSizeF(width, height)
        self._background_color: QColor = QColor("white")
        self._canvas_dpi: int = DEFAULT_CANVAS_DPI
        self._guides: list[Guide] = []
        self._update_scene_rect()

        self._layer_manager = LayerManager(self)
        self._command_stack = CommandStack(self)
        self._layer_manager.layer_visibility_changed.connect(self._on_layer_visibility_changed)
        self._layer_manager.layer_opacity_changed.connect(self._on_layer_opacity_changed)
        self._layer_manager.layer_blend_mode_changed.connect(self._on_layer_blend_mode_changed)
        # The content revision a blur region's cache keys on (Blur PRD 2.7; Basic Shape
        # remainder silence 3): every mutation is a command, and every layer change counts
        self._content_revision = 0
        self._command_stack.stack_changed.connect(self.bump_content_revision)
        for signal in (
            self._layer_manager.layer_added,
            self._layer_manager.layer_removed,
            self._layer_manager.layers_reordered,
            self._layer_manager.layer_visibility_changed,
            self._layer_manager.layer_opacity_changed,
            self._layer_manager.layer_blend_mode_changed,
        ):
            signal.connect(self.bump_content_revision)
        self.background_changed.connect(self.bump_content_revision)

        # Create default layer
        self._layer_manager.add_layer("Layer 1")

    # --- accessors ---

    @property
    def layer_manager(self) -> LayerManager:
        return self._layer_manager

    @property
    def command_stack(self) -> CommandStack:
        return self._command_stack

    @property
    def background_color(self) -> QColor:
        return QColor(self._background_color)

    def set_background_color(self, color: QColor) -> None:
        """Set the canvas background color."""
        self._background_color = QColor(color)
        self.background_changed.emit()
        self.update()

    @property
    def canvas_size(self) -> QSizeF:
        return QSizeF(self._canvas_size)

    @property
    def canvas_rect(self) -> QRectF:
        """Logical canvas bounds (0, 0, w, h) — use instead of sceneRect()."""
        return QRectF(0, 0, self._canvas_size.width(), self._canvas_size.height())

    def set_canvas_size(self, size: QSizeF) -> None:
        """Resize the logical canvas."""
        self._canvas_size = QSizeF(size)
        self._update_scene_rect()
        self.canvas_size_changed.emit(self._canvas_size)

    @property
    def canvas_dpi(self) -> int:
        """The project's nominal resolution (Technical Architecture PRD 4.1); 72 by default.

        Stored in the manifest; export keeps its own DPI setting.
        """
        return self._canvas_dpi

    def set_canvas_dpi(self, dpi: int) -> None:
        """Set the canvas DPI; change it through ``commands/canvas_property_commands.py``."""
        dpi = max(1, int(dpi))
        if dpi != self._canvas_dpi:
            self._canvas_dpi = dpi
            self.canvas_dpi_changed.emit(dpi)

    # --- the content revision (Blur PRD 2.7) ---

    @property
    def content_revision(self) -> int:
        """A counter that rises on every command, undo, redo, and layer or canvas colour
        change: a cache of what lies on the canvas is stale when it differs."""
        return self._content_revision

    def bump_content_revision(self, *_args: object) -> None:
        self._content_revision += 1

    # --- layer state on items (Technical Architecture PRD 3.9.1) ---

    def addItem(self, item: QGraphicsItem | None) -> None:  # noqa: N802
        super().addItem(item)
        self.apply_layer_state(item)

    def apply_layer_state(self, item: QGraphicsItem | None) -> None:
        """Give *item* its layer's visibility, opacity, and blend mode; a no-op otherwise."""
        from snapmock.items.base_item import SnapGraphicsItem

        if not isinstance(item, SnapGraphicsItem):
            return
        layer = self._layer_manager.layer_by_id(item.layer_id)
        if layer is None:
            return
        item.setVisible(layer.visible)
        item.layer_opacity = layer.opacity
        item.layer_blend_mode = layer.blend_mode

    # --- the two walks over annotation items (Group and Ungroup kickoff, step 5) ---
    # A group's members are its child items, so ``self.items()`` returns them beside the
    # group. A walk says which it means: the top-level items alone, or every item.

    def annotation_items(self) -> list[SnapGraphicsItem]:
        """The top-level annotation items: a group counts once and its members not at all."""
        from snapmock.items.base_item import SnapGraphicsItem

        return [
            i for i in self.items() if isinstance(i, SnapGraphicsItem) and i.parentItem() is None
        ]

    def all_annotation_items(self) -> list[SnapGraphicsItem]:
        """Every annotation item, groups and their members included."""
        from snapmock.items.base_item import SnapGraphicsItem

        return [i for i in self.items() if isinstance(i, SnapGraphicsItem)]

    def is_fixed_in_place(self, item: QGraphicsItem) -> bool:
        """Whether *item* is an image on a Background layer, which never moves.

        The image is the canvas (General UI PRD 6.2; end-to-end pass finding 11): no
        selection takes it, so no move, resize, nudge, or delete reaches it. Raster edits
        and the canvas operations still act on it.
        """
        from snapmock.items.raster_region_item import RasterRegionItem

        if not isinstance(item, RasterRegionItem) or item.parentItem() is not None:
            return False
        layer = self.layer_manager.layer_by_id(item.layer_id)
        return layer is not None and layer.is_background

    def items_on_layer(self, layer_id: str) -> list[QGraphicsItem]:
        """The top-level annotation items on *layer_id*."""
        return [i for i in self.annotation_items() if i.layer_id == layer_id]

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        for item in self.items_on_layer(layer_id):
            item.setVisible(visible)

    def _on_layer_opacity_changed(self, layer_id: str, opacity: float) -> None:
        from snapmock.items.base_item import SnapGraphicsItem

        for item in self.items_on_layer(layer_id):
            if isinstance(item, SnapGraphicsItem):
                item.layer_opacity = opacity

    def _on_layer_blend_mode_changed(self, layer_id: str, blend_mode: str) -> None:
        # Top-level items: a group carries the mode to its members
        from snapmock.items.base_item import SnapGraphicsItem

        for item in self.items_on_layer(layer_id):
            if isinstance(item, SnapGraphicsItem):
                item.layer_blend_mode = blend_mode

    # --- guides (General UI PRD 6.5); mutate through commands/guide_commands.py ---

    @property
    def guides(self) -> list[Guide]:
        return list(self._guides)

    def add_guide(self, guide: Guide) -> None:
        if guide not in self._guides:
            self._guides.append(guide)
            self._guides_did_change()

    def remove_guide(self, guide: Guide) -> None:
        if guide in self._guides:
            self._guides.remove(guide)
            self._guides_did_change()

    def replace_guide(self, old: Guide, new: Guide) -> None:
        if old in self._guides:
            self._guides[self._guides.index(old)] = new
            self._guides_did_change()

    def set_guides(self, guides: list[Guide]) -> None:
        self._guides = list(guides)
        self._guides_did_change()

    def _guides_did_change(self) -> None:
        self.guides_changed.emit()
        # Every view repaints its foreground through Qt's own scene-update path.
        self.update()

    def _update_scene_rect(self) -> None:
        """Expand sceneRect beyond the canvas to provide a pasteboard margin."""
        m = PASTEBOARD_MARGIN
        w = self._canvas_size.width()
        h = self._canvas_size.height()
        self.setSceneRect(QRectF(-m, -m, w + 2 * m, h + 2 * m))
