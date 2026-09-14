"""SnapStatusBar — the six zones of General UI PRD Section 9.

Left to right: the tool hint (flexible), cursor position (120 px), selection size
(120 px), canvas size (140 px), zoom level (80 px, clickable), memory usage (80 px,
refreshed every 5 seconds, warning colour above 500 MB and error colour above 1 GB).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QMenu, QStatusBar, QToolButton, QWidget

from snapmock.config.constants import APP_NAME
from snapmock.core.process_memory import format_memory, memory_role, process_memory_bytes
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.ui.toolbar import ZOOM_PRESETS

if TYPE_CHECKING:
    from PyQt6.QtCore import QRectF, QSizeF

    from snapmock.core.document import Document
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.core.view import SnapView

STATUS_BAR_HEIGHT = 24
CURSOR_ZONE_WIDTH = 120
SELECTION_ZONE_WIDTH = 120
CANVAS_ZONE_WIDTH = 140
ZOOM_ZONE_WIDTH = 80
MEMORY_ZONE_WIDTH = 80
MEMORY_REFRESH_MS = 5_000


class SnapStatusBar(QStatusBar):
    """Status bar following the active document's view, selection, and scene."""

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view: SnapView = document.view
        self._selection: SelectionManager = document.selection_manager
        self._scene: SnapScene = document.scene
        self.setFixedHeight(STATUS_BAR_HEIGHT)
        self.setAccessibleName("Status bar")

        # The hint zone is the message a screen reader hears (PRD 14): a QLabel with
        # no accessible name of its own reports each text change as a name change.
        self._hint_label = QLabel("")
        self._hint_label.setAccessibleDescription("Status message")
        self._cursor_label = self._zone(CURSOR_ZONE_WIDTH)
        self._selection_label = self._zone(SELECTION_ZONE_WIDTH)
        self._canvas_label = self._zone(CANVAS_ZONE_WIDTH)
        self._zoom_button = QToolButton()
        self._zoom_button.setAutoRaise(True)
        self._zoom_button.setFixedWidth(ZOOM_ZONE_WIDTH)
        self._zoom_button.setToolTip("Zoom level. Click to choose a preset.")
        self._zoom_button.setAccessibleName("Zoom level")
        self._zoom_button.setAccessibleDescription("Opens the zoom preset menu.")
        self._zoom_button.clicked.connect(self._show_zoom_menu)
        self._memory_label = self._zone(MEMORY_ZONE_WIDTH)
        self._memory_label.setToolTip(f"Memory used by {APP_NAME}")

        self.addWidget(self._hint_label, 1)
        for widget in (
            self._cursor_label,
            self._selection_label,
            self._canvas_label,
            self._zoom_button,
            self._memory_label,
        ):
            self.addPermanentWidget(widget)

        self.update_cursor_pos(0, 0)
        self._connect_document()
        self._on_zoom_changed(self._view.zoom_percent)
        self._refresh_selection_size()
        self._on_canvas_size_changed(self._scene.canvas_size)

        self._memory_timer = QTimer(self)
        self._memory_timer.setInterval(MEMORY_REFRESH_MS)
        self._memory_timer.timeout.connect(self.refresh_memory)
        self._memory_timer.start()
        self.refresh_memory()

    @staticmethod
    def _zone(width: int) -> QLabel:
        label = QLabel("")
        label.setFixedWidth(width)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return label

    # ---- document binding ----

    def _connect_document(self) -> None:
        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._selection.selection_changed.connect(self._on_selection_changed)
        self._scene.canvas_size_changed.connect(self._on_canvas_size_changed)
        self._scene.changed.connect(self._on_scene_changed)

    def _disconnect_document(self) -> None:
        for signal, slot in (
            (self._view.zoom_changed, self._on_zoom_changed),
            (self._selection.selection_changed, self._on_selection_changed),
            (self._scene.canvas_size_changed, self._on_canvas_size_changed),
            (self._scene.changed, self._on_scene_changed),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def set_document(self, document: Document) -> None:
        """Follow another document (tab switch): its view, selection, and scene."""
        if document.view is self._view:
            return
        self._disconnect_document()
        self._view = document.view
        self._selection = document.selection_manager
        self._scene = document.scene
        self._connect_document()
        self._on_zoom_changed(self._view.zoom_percent)
        self._refresh_selection_size()
        self._on_canvas_size_changed(self._scene.canvas_size)

    def set_view(self, view: SnapView) -> None:
        """Compatibility: the view alone; :meth:`set_document` rebinds every zone."""
        if view is self._view:
            return
        try:
            self._view.zoom_changed.disconnect(self._on_zoom_changed)
        except (TypeError, RuntimeError):
            pass
        self._view = view
        view.zoom_changed.connect(self._on_zoom_changed)
        self._on_zoom_changed(view.zoom_percent)

    # ---- zones ----

    def set_hint(self, text: str) -> None:
        """The tool hint zone."""
        self._hint_label.setText(text)

    def update_cursor_pos(self, x: float, y: float) -> None:
        self._cursor_label.setText(f"X: {x:.0f} Y: {y:.0f}")

    def _on_selection_changed(self, _items: list[object]) -> None:
        self._refresh_selection_size()

    def _on_scene_changed(self, _regions: list[QRectF]) -> None:
        if self._selection.count:
            self._refresh_selection_size()

    def _refresh_selection_size(self) -> None:
        items = [i for i in self._selection.items if isinstance(i, SnapGraphicsItem)]
        if not items:
            self._selection_label.setText("")
            return
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        self._selection_label.setText(f"W: {rect.width():.0f} H: {rect.height():.0f}")

    def _on_canvas_size_changed(self, size: QSizeF) -> None:
        self._canvas_label.setText(f"Canvas: {size.width():.0f} x {size.height():.0f}")

    def _on_zoom_changed(self, percent: int) -> None:
        self._zoom_button.setText(f"{percent}%")

    def zoom_menu(self) -> QMenu:
        """The preset menu the zoom zone opens (the Main Toolbar's dropdown presets)."""
        menu = QMenu(self)
        current = self._view.zoom_percent
        for preset in ZOOM_PRESETS:
            action = menu.addAction(f"{preset}%")
            if action is not None:
                action.setCheckable(True)
                action.setChecked(preset == current)
                action.triggered.connect(lambda _checked=False, p=preset: self._view.set_zoom(p))
        return menu

    def _show_zoom_menu(self) -> None:
        menu = self.zoom_menu()
        menu.exec(self._zoom_button.mapToGlobal(self._zoom_button.rect().topLeft()))

    def refresh_memory(self) -> None:
        """Re-read the process memory (every 5 seconds, PRD 9) and recolour the zone."""
        self.set_memory_bytes(process_memory_bytes())

    def set_memory_bytes(self, nbytes: int | None) -> None:
        self._memory_label.setText(format_memory(nbytes))
        role = memory_role(nbytes)
        if self._memory_label.property("role") != role:
            self._memory_label.setProperty("role", role)
            style = self._memory_label.style()
            if style is not None:
                style.unpolish(self._memory_label)
                style.polish(self._memory_label)

    @property
    def memory_label(self) -> QLabel:
        return self._memory_label
