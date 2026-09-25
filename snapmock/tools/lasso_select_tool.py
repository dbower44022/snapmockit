"""LassoSelectTool — freeform and polygonal raster selection."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainterPath, QPen
from PyQt6.QtWidgets import QComboBox, QLabel, QToolBar

from snapmock.core.path_utils import simplify_rdp
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.selection_overlay import SelectionOverlay

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsPathItem

    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager


class _LassoMode(Enum):
    FREEFORM = auto()
    POLYGONAL = auto()


class _LassoState(Enum):
    IDLE = auto()
    DRAWING = auto()
    ACTIVE = auto()
    MOVING = auto()


class LassoSelectTool(BaseTool):
    """Freeform and polygonal lasso selection for raster operations."""

    def __init__(self) -> None:
        super().__init__()
        self._mode: _LassoMode = _LassoMode.FREEFORM
        self._state: _LassoState = _LassoState.IDLE
        self._points: list[QPointF] = []
        self._path_item: QGraphicsPathItem | None = None
        self._overlay: SelectionOverlay | None = None
        self._drag_start: QPointF = QPointF()

    @property
    def tool_id(self) -> str:
        return "lasso_select"

    @property
    def display_name(self) -> str:
        return "Lasso Select"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def is_active_operation(self) -> bool:
        return self._state in (_LassoState.DRAWING, _LassoState.MOVING)

    @property
    def has_active_selection(self) -> bool:
        return self._state == _LassoState.ACTIVE and self._overlay is not None

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
        if self._path_item is not None and self._scene is not None:
            self._scene.removeItem(self._path_item)
            self._path_item = None
        if self._overlay is not None:
            self._overlay.remove_from_scene()
            self._overlay = None
        self._state = _LassoState.IDLE
        self._points.clear()

    def _scene_pos(self, event: QMouseEvent) -> QPointF | None:
        view = self._view
        if view is not None:
            return view.mapToScene(event.pos())
        return None

    def _update_drawing_path(self) -> None:
        """Update the visual drawing path during freeform/polygonal drawing."""
        if self._scene is None or not self._points:
            return

        from PyQt6.QtWidgets import QGraphicsPathItem

        path = QPainterPath()
        path.moveTo(self._points[0])
        for pt in self._points[1:]:
            path.lineTo(pt)

        if self._path_item is None:
            self._path_item = QGraphicsPathItem()
            self._path_item.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
            self._path_item.setZValue(999999)
            self._scene.addItem(self._path_item)

        self._path_item.setPath(path)

    def _finalize_selection(self) -> None:
        """Close the path and transition to ACTIVE state with marching ants."""
        if self._scene is None or len(self._points) < 3:
            self.cancel()
            return

        # Remove drawing path
        if self._path_item is not None:
            self._scene.removeItem(self._path_item)
            self._path_item = None

        # Simplify path
        simplified = simplify_rdp(self._points, epsilon=2.0)

        # Build closed painter path
        path = QPainterPath()
        path.moveTo(simplified[0])
        for pt in simplified[1:]:
            path.lineTo(pt)
        path.closeSubpath()

        # Create overlay with freeform path
        self._overlay = SelectionOverlay(self._scene)
        self._overlay.set_selection_path(path)
        self._overlay.add_to_scene()
        self._state = _LassoState.ACTIVE

    # --- mouse events ---

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _LassoState.ACTIVE and self._overlay is not None:
            # Check inside for move
            if self._overlay.is_inside(pos):
                self._drag_start = pos
                self._state = _LassoState.MOVING
                return True
            # Click outside = cancel and start new
            self._overlay.remove_from_scene()
            self._overlay = None

        if self._mode == _LassoMode.FREEFORM:
            self._points = [pos]
            self._state = _LassoState.DRAWING
            self._update_drawing_path()
            return True

        if self._mode == _LassoMode.POLYGONAL:
            if self._state == _LassoState.IDLE:
                self._points = [pos]
                self._state = _LassoState.DRAWING
            else:
                self._points.append(pos)
            self._update_drawing_path()
            return True

        return False

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._scene is None:
            return False
        pos = self._scene_pos(event)
        if pos is None:
            return False

        if self._state == _LassoState.DRAWING and self._mode == _LassoMode.FREEFORM:
            self._points.append(pos)
            self._update_drawing_path()
            return True

        if self._state == _LassoState.DRAWING and self._mode == _LassoMode.POLYGONAL:
            # Show preview line to cursor
            return True

        if self._state == _LassoState.MOVING and self._overlay is not None:
            delta = pos - self._drag_start
            src_path = self._overlay._selection_path  # noqa: SLF001
            new_path = QPainterPath(src_path) if src_path is not None else QPainterPath()
            new_path.translate(delta)
            self._overlay.set_selection_path(new_path)
            self._drag_start = pos
            return True

        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._state == _LassoState.DRAWING and self._mode == _LassoMode.FREEFORM:
            self._finalize_selection()
            return True

        if self._state == _LassoState.MOVING:
            self._state = _LassoState.ACTIVE
            return True

        return False

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        if self._state == _LassoState.DRAWING and self._mode == _LassoMode.POLYGONAL:
            self._finalize_selection()
            return True
        return False

    # --- key events ---

    def handle_escape(self) -> bool:
        """Escape drops the lasso in progress or the marquee (Navigation PRD Section 6);
        with none it leaves the tool to the window's ladder (General UI PRD 2.58)."""
        if self._state == _LassoState.IDLE:
            return False
        self.cancel()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._state == _LassoState.ACTIVE:
                self._commit_as_item()
                return True
            if self._state == _LassoState.DRAWING and self._mode == _LassoMode.POLYGONAL:
                self._finalize_selection()
                return True

        # Right-click or Backspace removes last vertex in polygonal mode
        if event.key() == Qt.Key.Key_Backspace:
            if (
                self._state == _LassoState.DRAWING
                and self._mode == _LassoMode.POLYGONAL
                and len(self._points) > 1
            ):
                self._points.pop()
                self._update_drawing_path()
                return True

        return False

    # --- commit to item ---

    def _commit_as_item(self) -> None:
        """Commit the current lasso selection as a masked RasterRegionItem."""
        if self._scene is None or self._overlay is None:
            return
        from PyQt6.QtGui import QImage, QPixmap

        from snapmock.commands.add_item import AddItemCommand
        from snapmock.core.render_engine import RenderEngine
        from snapmock.items.raster_region_item import RasterRegionItem

        rect = self._overlay.selection_rect
        if rect.isEmpty():
            return

        # Render the bounding region
        engine = RenderEngine(self._scene)
        image = engine.render_region(rect)

        # Apply freeform path as alpha mask
        sel_path = self._overlay._selection_path  # noqa: SLF001
        if sel_path is not None:
            from PyQt6.QtGui import QPainter

            masked = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
            masked.fill(Qt.GlobalColor.transparent)
            painter = QPainter(masked)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Translate path to local coords
            local_path = QPainterPath(sel_path)
            local_path.translate(-rect.topLeft())
            painter.setClipPath(local_path)
            painter.drawImage(0, 0, image)
            painter.end()
            image = masked

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
        if self._state == _LassoState.IDLE:
            if self._mode == _LassoMode.FREEFORM:
                return "Click and drag to draw freeform selection"
            return "Click to add vertices, double-click or Enter to close"
        if self._state == _LassoState.DRAWING:
            if self._mode == _LassoMode.FREEFORM:
                return "Release to close selection path"
            return "Click to add vertex | Enter/double-click to close | Backspace to undo"
        if self._state == _LassoState.ACTIVE:
            return "Enter: commit as item | Ctrl+C: copy | Drag to move"
        return ""

    # --- tool options ---

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        toolbar.addWidget(QLabel("Mode:"))
        combo = QComboBox()
        combo.setAccessibleName("Lasso mode")
        combo.setToolTip("Freeform or polygonal lasso")
        combo.addItems(["Freeform", "Polygonal"])
        combo.currentTextChanged.connect(self._on_mode_changed)
        toolbar.addWidget(combo)

        toolbar.addSeparator()
        from PyQt6.QtWidgets import QCheckBox, QSpinBox

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

    def _on_mode_changed(self, text: str) -> None:
        if text == "Freeform":
            self._mode = _LassoMode.FREEFORM
        else:
            self._mode = _LassoMode.POLYGONAL
        self.cancel()
