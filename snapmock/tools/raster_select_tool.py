"""RasterSelectTool — rectangular pixel selection with marching ants."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QCursor, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QCheckBox, QLabel, QSpinBox, QToolBar

from snapmock.config.constants import DRAG_THRESHOLD
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.cursors import raster_select_cursor
from snapmock.ui.dimension_overlay import dimension_overlay, existing_dimension_overlay
from snapmock.ui.selection_overlay import SelectionOverlay

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager


class _RasterState(Enum):
    IDLE = auto()
    DRAWING = auto()
    ACTIVE = auto()
    MOVING = auto()
    RESIZING = auto()


class RasterSelectTool(BaseTool):
    """Draw a rectangular selection for raster copy/cut/paste operations."""

    def __init__(self) -> None:
        super().__init__()
        self._state: _RasterState = _RasterState.IDLE
        self._start: QPointF = QPointF()
        self._overlay: SelectionOverlay | None = None
        self._drag_start: QPointF = QPointF()
        self._active_handle: str | None = None

    @property
    def tool_id(self) -> str:
        return "raster_select"

    @property
    def display_name(self) -> str:
        return "Raster Select"

    @property
    def cursor(self) -> QCursor:
        """Crosshair with a dotted square (General UI PRD 6.6)."""
        return raster_select_cursor()

    @property
    def is_active_operation(self) -> bool:
        return self._state in (_RasterState.DRAWING, _RasterState.MOVING, _RasterState.RESIZING)

    @property
    def has_active_selection(self) -> bool:
        return self._state == _RasterState.ACTIVE and self._overlay is not None

    @property
    def selection_rect(self) -> QRectF:
        if self._overlay is not None:
            return self._overlay.selection_rect
        return QRectF()

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)

    def deactivate(self) -> None:
        self.cancel()
        super().deactivate()

    def cancel(self) -> None:
        if self._overlay is not None:
            self._overlay.remove_from_scene()
            self._overlay = None
        self._state = _RasterState.IDLE
        self._active_handle = None
        self._hide_size_readout()

    def _hide_size_readout(self) -> None:
        """Take the W / H readout down: the selection is drawn or cancelled."""
        view = self._view
        viewport = view.viewport() if view is not None else None
        overlay = existing_dimension_overlay(viewport) if viewport is not None else None
        if overlay is not None:
            overlay.hide_feedback()

    def _scene_pos(self, event: QMouseEvent) -> QPointF | None:
        view = self._view
        if view is not None:
            return view.mapToScene(event.pos())
        return None

    def _ensure_overlay(self) -> SelectionOverlay:
        if self._overlay is None and self._scene is not None:
            self._overlay = SelectionOverlay(self._scene)
        assert self._overlay is not None
        return self._overlay

    # --- mouse events ---

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _RasterState.ACTIVE and self._overlay is not None:
            # Check for handle hit
            handle = self._overlay.handle_at(pos)
            if handle is not None:
                self._active_handle = handle
                self._drag_start = pos
                self._state = _RasterState.RESIZING
                return True

            # Check for interior hit (move marquee)
            if self._overlay.is_inside(pos):
                self._drag_start = pos
                self._state = _RasterState.MOVING
                return True

            # Click outside — cancel and begin new
            self._overlay.remove_from_scene()
            self._overlay = None

        # Start new selection
        self._start = pos
        # Clip to canvas bounds
        canvas = self._scene.canvas_rect
        if not canvas.contains(self._start):
            self._start = QPointF(
                max(canvas.left(), min(canvas.right(), self._start.x())),
                max(canvas.top(), min(canvas.bottom(), self._start.y())),
            )
        self._state = _RasterState.DRAWING
        overlay = self._ensure_overlay()
        overlay.set_selection_rect(QRectF(self._start, self._start))
        overlay.add_to_scene()
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._scene is None:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _RasterState.DRAWING:
            # Clip to canvas
            canvas = self._scene.canvas_rect
            clamped = QPointF(
                max(canvas.left(), min(canvas.right(), pos.x())),
                max(canvas.top(), min(canvas.bottom(), pos.y())),
            )

            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

            if alt:
                # Alt: resize from center (start is center)
                dx = abs(clamped.x() - self._start.x())
                dy = abs(clamped.y() - self._start.y())
                if shift:
                    dx = dy = min(dx, dy)
                rect = QRectF(
                    self._start.x() - dx,
                    self._start.y() - dy,
                    dx * 2,
                    dy * 2,
                )
            else:
                rect = QRectF(self._start, clamped).normalized()
                if shift:
                    # Square constraint keeping anchor corner stable
                    side = min(rect.width(), rect.height())
                    if clamped.x() < self._start.x():
                        rect.setLeft(self._start.x() - side)
                    else:
                        rect.setRight(self._start.x() + side)
                    if clamped.y() < self._start.y():
                        rect.setTop(self._start.y() - side)
                    else:
                        rect.setBottom(self._start.y() + side)

            overlay = self._ensure_overlay()
            overlay.set_selection_rect(rect)

            # The W / H readout, on the widget over the viewport and never a Qt tooltip
            # window (end-to-end pass finding 3, with the Select tool's move readout)
            view = self._view
            viewport = view.viewport() if view is not None else None
            if viewport is not None:
                dimension_overlay(viewport).show_measurement(
                    event.pos(), f"W: {rect.width():.0f}  H: {rect.height():.0f}", False, None
                )
            return True

        if self._state == _RasterState.MOVING and self._overlay is not None:
            delta = pos - self._drag_start
            old_rect = self._overlay.selection_rect
            new_rect = old_rect.translated(delta)
            self._overlay.set_selection_rect(new_rect)
            self._drag_start = pos
            return True

        if self._state == _RasterState.RESIZING and self._overlay is not None:
            return self._handle_resize(pos)

        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._state == _RasterState.DRAWING:
            self._hide_size_readout()
            pos = self._scene_pos(event)
            if pos is not None and self._overlay is not None:
                rect = self._overlay.selection_rect
                if rect.width() > DRAG_THRESHOLD and rect.height() > DRAG_THRESHOLD:
                    self._state = _RasterState.ACTIVE
                else:
                    # Too small, cancel
                    self.cancel()
            else:
                self.cancel()
            return True

        if self._state in (_RasterState.MOVING, _RasterState.RESIZING):
            self._state = _RasterState.ACTIVE
            self._active_handle = None
            return True

        return False

    # --- key events ---

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            if self._state != _RasterState.IDLE:
                self.cancel()
                return True

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._state == _RasterState.ACTIVE:
                self._commit_as_item()
                return True

        return False

    # --- handle resize ---

    def _handle_resize(self, pos: QPointF) -> bool:
        if self._overlay is None or self._active_handle is None:
            return False
        rect = QRectF(self._overlay.selection_rect)

        if "left" in self._active_handle:
            rect.setLeft(pos.x())
        if "right" in self._active_handle:
            rect.setRight(pos.x())
        if "top" in self._active_handle:
            rect.setTop(pos.y())
        if "bottom" in self._active_handle:
            rect.setBottom(pos.y())
        if self._active_handle == "top_center":
            rect.setTop(pos.y())
        if self._active_handle == "bottom_center":
            rect.setBottom(pos.y())
        if self._active_handle == "middle_left":
            rect.setLeft(pos.x())
        if self._active_handle == "middle_right":
            rect.setRight(pos.x())

        rect = rect.normalized()
        self._overlay.set_selection_rect(rect)
        return True

    # --- pixel operations ---

    def _commit_as_item(self) -> None:
        """Commit the current selection as a RasterRegionItem on the active layer."""
        if self._scene is None or self._overlay is None:
            return
        from snapmock.commands.add_item import AddItemCommand
        from snapmock.core.render_engine import RenderEngine
        from snapmock.items.raster_region_item import RasterRegionItem

        rect = self._overlay.selection_rect
        if rect.isEmpty():
            return

        # Render the selection region
        engine = RenderEngine(self._scene)
        image = engine.render_region(rect)

        from PyQt6.QtGui import QPixmap

        pixmap = QPixmap.fromImage(image)
        item = RasterRegionItem(pixmap=pixmap)
        item.setPos(rect.topLeft())

        layer = self._scene.layer_manager.active_layer
        if layer is not None:
            cmd = AddItemCommand(self._scene, item, layer.layer_id)
            self._scene.command_stack.push(cmd)

        self.cancel()

    @property
    def status_hint(self) -> str:
        if self._state == _RasterState.IDLE:
            return "Click and drag to draw a rectangular selection"
        if self._state == _RasterState.DRAWING:
            return "Shift: square | Alt: from center | Release to finish"
        if self._state == _RasterState.ACTIVE:
            return "Enter: commit as item | Ctrl+C: copy | Drag to move"
        return ""

    # --- tool options ---

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        self._info_label = QLabel("Draw a selection rectangle")
        toolbar.addWidget(self._info_label)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Feather:"))
        feather = QSpinBox()
        feather.setAccessibleName("Feather")
        feather.setToolTip("Feather the selection's edge")
        feather.setRange(0, 20)
        feather.setValue(0)
        feather.setSuffix("px")
        toolbar.addWidget(feather)

        antialias = QCheckBox("Anti-alias")
        antialias.setChecked(True)
        toolbar.addWidget(antialias)
