"""SelectionManager — tracks the set of currently selected scene items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene


class SelectionManager(QObject):
    """Tracks which items are selected and provides operations on the selection.

    Signals
    -------
    selection_changed(list)
        Emitted with the list of currently selected items.
    selection_cleared()
        Emitted when all items are deselected.
    """

    selection_changed = pyqtSignal(list)
    selection_cleared = pyqtSignal()

    def __init__(self, scene: SnapScene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._selected: list[QGraphicsItem] = []

    @property
    def items(self) -> list[QGraphicsItem]:
        return list(self._selected)

    @property
    def count(self) -> int:
        return len(self._selected)

    @property
    def is_empty(self) -> bool:
        return len(self._selected) == 0

    def select(self, item: QGraphicsItem, *, add: bool = False) -> None:
        """Select an item. If *add* is False, deselect everything else first."""
        if not add:
            self._deselect_all_internal()
        if item not in self._selected and not self._scene.is_fixed_in_place(item):
            self._selected.append(item)
            item.setSelected(True)
        self.selection_changed.emit(self._selected)

    def toggle(self, item: QGraphicsItem) -> None:
        """Toggle selection state of *item*."""
        if sip.isdeleted(item):
            self._selected = [i for i in self._selected if not sip.isdeleted(i)]
            self.selection_changed.emit(self._selected)
            return
        if item in self._selected:
            self._selected.remove(item)
            item.setSelected(False)
        elif not self._scene.is_fixed_in_place(item):
            self._selected.append(item)
            item.setSelected(True)
        self.selection_changed.emit(self._selected)

    def select_items(self, items: list[QGraphicsItem]) -> None:
        """Replace the selection with *items*."""
        self._deselect_all_internal()
        for item in items:
            if self._scene.is_fixed_in_place(item):
                continue
            self._selected.append(item)
            item.setSelected(True)
        self.selection_changed.emit(self._selected)

    def deselect_all(self) -> None:
        """Clear the selection."""
        if self._selected:
            self._deselect_all_internal()
            self.selection_cleared.emit()
            self.selection_changed.emit(self._selected)

    def _deselect_all_internal(self) -> None:
        for item in self._selected:
            if not sip.isdeleted(item):
                item.setSelected(False)
        self._selected.clear()
