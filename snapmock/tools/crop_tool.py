"""CropTool — interactive crop with overlay, handles, and state machine."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QToolBar

from snapmock.commands.raster_commands import CropCanvasCommand
from snapmock.config.constants import DRAG_THRESHOLD
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.crop_overlay import CropOverlay

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager


class _CropState(Enum):
    IDLE = auto()
    DRAWING = auto()
    ADJUSTING = auto()
    MOVING = auto()
    RESIZING = auto()


# Preset aspect ratios (width/height or None for free)
_ASPECT_PRESETS: dict[str, float | None] = {
    "Free": None,
    "1:1": 1.0,
    "4:3": 4.0 / 3.0,
    "16:9": 16.0 / 9.0,
    "3:2": 3.0 / 2.0,
}


class CropTool(BaseTool):
    """Interactive crop tool with visual overlay and state machine."""

    def __init__(self) -> None:
        super().__init__()
        self._state: _CropState = _CropState.IDLE
        self._overlay: CropOverlay | None = None
        self._start: QPointF = QPointF()
        self._drag_start: QPointF = QPointF()
        self._active_handle: str | None = None
        self._aspect_ratio: float | None = None
        self._show_grid: bool = True

    @property
    def tool_id(self) -> str:
        return "crop"

    @property
    def display_name(self) -> str:
        return "Crop"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def is_active_operation(self) -> bool:
        return self._state in (_CropState.DRAWING, _CropState.MOVING, _CropState.RESIZING)

    @property
    def status_hint(self) -> str:
        return "Drag to define crop area | Enter to apply | Escape to cancel"

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        self._overlay = CropOverlay(scene)
        # Start with full-canvas crop region
        canvas_rect = QRectF(QPointF(0, 0), scene.canvas_size)
        self._overlay.update_crop_rect(canvas_rect)
        self._overlay.add_to_scene()
        self._state = _CropState.ADJUSTING

    def deactivate(self) -> None:
        self.cancel()
        super().deactivate()

    def cancel(self) -> None:
        if self._overlay is not None:
            self._overlay.remove_from_scene()
            self._overlay = None
        self._state = _CropState.IDLE
        self._active_handle = None

    def _scene_pos(self, event: QMouseEvent) -> QPointF | None:
        view = self._view
        if view is not None:
            return view.mapToScene(event.pos())
        return None

    def _constrain_rect(self, rect: QRectF) -> QRectF:
        """Apply aspect ratio constraint if set."""
        if self._aspect_ratio is None:
            return rect
        w = rect.width()
        h = rect.height()
        if w / max(h, 1) > self._aspect_ratio:
            rect.setWidth(h * self._aspect_ratio)
        else:
            rect.setHeight(w / self._aspect_ratio)
        return rect

    # --- mouse events ---

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _CropState.ADJUSTING and self._overlay is not None:
            # Check for handle hit
            handle = self._overlay.handle_at(pos)
            if handle is not None:
                self._active_handle = handle
                self._drag_start = pos
                self._state = _CropState.RESIZING
                return True

            # Check for interior hit (move crop)
            if self._overlay.is_inside_crop(pos):
                self._drag_start = pos
                self._state = _CropState.MOVING
                return True

            # Click outside — start new crop region
            self._start = pos
            self._state = _CropState.DRAWING
            return True

        if self._state == _CropState.IDLE:
            self._start = pos
            self._state = _CropState.DRAWING
            if self._overlay is None and self._scene is not None:
                self._overlay = CropOverlay(self._scene)
                self._overlay.add_to_scene()
            return True

        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._scene is None or self._overlay is None:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _CropState.DRAWING:
            rect = QRectF(self._start, pos).normalized()
            rect = self._constrain_rect(rect)
            self._overlay.update_crop_rect(rect)
            return True

        if self._state == _CropState.MOVING:
            delta = pos - self._drag_start
            old_rect = self._overlay.crop_rect
            new_rect = old_rect.translated(delta)
            self._overlay.update_crop_rect(new_rect)
            self._drag_start = pos
            return True

        if self._state == _CropState.RESIZING:
            return self._handle_resize(pos)

        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._scene is None or self._overlay is None:
            return False

        if self._state == _CropState.DRAWING:
            pos = self._scene_pos(event)
            if pos is not None:
                rect = QRectF(self._start, pos).normalized()
                rect = self._constrain_rect(rect)
                if rect.width() > DRAG_THRESHOLD and rect.height() > DRAG_THRESHOLD:
                    self._overlay.update_crop_rect(rect)
                    self._state = _CropState.ADJUSTING
                else:
                    self._state = _CropState.ADJUSTING
            else:
                self._state = _CropState.ADJUSTING
            return True

        if self._state in (_CropState.MOVING, _CropState.RESIZING):
            self._state = _CropState.ADJUSTING
            self._active_handle = None
            return True

        return True

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        """Double-click inside the crop rect commits the crop."""
        if self._state == _CropState.ADJUSTING:
            self._commit_crop()
            return True
        return False

    # --- key events ---

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self._state == _CropState.ADJUSTING:
                self._commit_crop()
                return True
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            # Re-enter with full canvas if scene is still set
            if self._scene is not None:
                self._overlay = CropOverlay(self._scene)
                canvas_rect = QRectF(QPointF(0, 0), self._scene.canvas_size)
                self._overlay.update_crop_rect(canvas_rect)
                self._overlay.add_to_scene()
                self._state = _CropState.ADJUSTING
            return True
        return False

    # --- handle resize ---

    def _handle_resize(self, pos: QPointF) -> bool:
        if self._overlay is None or self._active_handle is None:
            return False
        rect = QRectF(self._overlay.crop_rect)

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
        rect = self._constrain_rect(rect)
        self._overlay.update_crop_rect(rect)
        return True

    # --- commit ---

    def _commit_crop(self) -> None:
        if self._scene is None or self._overlay is None:
            return
        crop_rect = self._overlay.crop_rect
        if crop_rect.width() > 1 and crop_rect.height() > 1:
            cmd = CropCanvasCommand(self._scene, crop_rect)
            self._scene.command_stack.push(cmd)
        # Reset to new full canvas
        self.cancel()
        if self._scene is not None:
            self._overlay = CropOverlay(self._scene)
            canvas_rect = QRectF(QPointF(0, 0), self._scene.canvas_size)
            self._overlay.update_crop_rect(canvas_rect)
            self._overlay.add_to_scene()
            self._state = _CropState.ADJUSTING

    # --- tool options ---

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        toolbar.addWidget(QLabel("Aspect:"))
        combo = QComboBox()
        combo.setAccessibleName("Aspect ratio")
        combo.setToolTip("Aspect ratio")
        for name in _ASPECT_PRESETS:
            combo.addItem(name)
        combo.currentTextChanged.connect(self._on_aspect_changed)
        toolbar.addWidget(combo)

        grid_cb = QCheckBox("Rule of Thirds")
        grid_cb.setChecked(self._show_grid)
        grid_cb.toggled.connect(self._on_grid_toggled)
        toolbar.addWidget(grid_cb)

    def _on_aspect_changed(self, text: str) -> None:
        self._aspect_ratio = _ASPECT_PRESETS.get(text)

    def _on_grid_toggled(self, checked: bool) -> None:
        self._show_grid = checked
        if self._overlay is not None:
            self._overlay.set_show_grid(checked)
