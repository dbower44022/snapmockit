"""SelectTool — click-select, drag-move, rubber-band multi-select, nudge, transform."""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QKeyEvent, QMouseEvent, QPen, QTransform
from PyQt6.QtWidgets import QGraphicsRectItem

from snapmock.commands.move_items import MoveItemsCommand
from snapmock.config.constants import (
    DEFAULT_BLUR_BRUSH_SIZE,
    DRAG_THRESHOLD,
    GRID_SIZE_DEFAULT,
    MIN_TEXT_BOX_HEIGHT,
)
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.blur_item import BlurItem
from snapmock.items.callout_item import CalloutItem
from snapmock.items.emoji_item import EmojiItem
from snapmock.items.group_item import GroupItem
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.items.stamp_item import StampItem
from snapmock.items.text_item import TextItem
from snapmock.tools.base_tool import BaseTool
from snapmock.tools.blur_edit import BlurBrushSession, brush_editable
from snapmock.tools.point_edit import PointEditSession, PointHandlesItem, session_for
from snapmock.ui.dimension_overlay import dimension_overlay, existing_dimension_overlay
from snapmock.ui.transform_handles import (
    CORNER_HANDLES,
    EDGE_HANDLES,
    HandlePosition,
    TransformHandles,
)

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager


class _State(Enum):
    IDLE = auto()
    RUBBER_BAND = auto()
    DRAGGING = auto()
    HANDLE_DRAG = auto()
    POINT_DRAG = auto()
    BRUSH_STROKE = auto()


class SelectTool(BaseTool):
    """The default selection and move tool with rubber-band, nudge, and transform handles."""

    def __init__(self) -> None:
        super().__init__()
        self._state: _State = _State.IDLE
        self._press_pos: QPointF = QPointF()
        self._drag_start: QPointF = QPointF()
        self._drag_items: list[SnapGraphicsItem] = []
        self._drag_total: QPointF = QPointF()
        self._constrain_axis: str | None = None  # "x" or "y" when Shift is held

        # Rubber-band
        self._rubber_band: QGraphicsRectItem | None = None

        # Transform handles
        self._handles: TransformHandles | None = None

        # Handle-drag state
        self._handle_pos: HandlePosition | None = None
        self._handle_origin_rect: QRectF = QRectF()
        self._handle_anchor: QPointF = QPointF()
        self._handle_item_originals: list[tuple[SnapGraphicsItem, QPointF, QTransform]] = []
        # Original geometry for text items (keyed by id(item))
        self._text_originals: dict[int, dict[str, Any]] = {}
        # Set by a double-click on a group; shown in the status bar (kickoff silence 1)
        self._group_hint: bool = False
        # Point-editing mode (Basic Shape PRD 3.5; Basic Shape remainder decision 1)
        self._point_session: PointEditSession | None = None
        self._point_handles: PointHandlesItem | None = None
        # Brush-editing mode of a freeform blur region (Blur PRD 2.8; freeform blur
        # silence 3): the Select tool's second mode, never live while the first is
        self._brush_session: BlurBrushSession | None = None
        # The view whose zoom_changed the brush cursor follows while the tool is active
        self._zoom_view: Any = None

    @property
    def tool_id(self) -> str:
        return "select"

    @property
    def display_name(self) -> str:
        return "Select"

    @property
    def cursor(self) -> Qt.CursorShape | QCursor:
        """The arrow, or the brush circle while brush editing lasts (Blur PRD 2.8)."""
        session = self._brush_session
        if session is None:
            return Qt.CursorShape.ArrowCursor
        from snapmock.ui.cursors import brush_cursor

        view = self._view
        zoom = (view.zoom_percent / 100.0) if view is not None else 1.0
        return brush_cursor(round(session.brush_size * zoom))

    @property
    def is_active_operation(self) -> bool:
        return self._state in (
            _State.DRAGGING,
            _State.RUBBER_BAND,
            _State.HANDLE_DRAG,
            _State.POINT_DRAG,
            _State.BRUSH_STROKE,
        )

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        self._handles = TransformHandles(scene)
        self._update_handles()
        if selection_manager is not None:
            selection_manager.selection_changed.connect(self._on_selection_changed)
        view = self._view
        if view is not None:
            # The brush-editing cursor is drawn in screen pixels, so it follows the zoom
            # (General UI PRD 6.6; found by the Freehand remainder work, 09-13-26)
            view.zoom_changed.connect(self._on_zoom_changed)
            self._zoom_view = view

    def _on_zoom_changed(self, _percent: int) -> None:
        if self._brush_session is not None:
            self._refresh_cursor()

    def apply_theme(self) -> None:
        """Recolour the transform handles after a theme switch (General UI PRD 13.4)."""
        if self._handles is not None:
            self._handles.apply_theme()

    def deactivate(self) -> None:
        self.cancel()
        view = self._view
        if view is not None:
            view.set_hover_cursor(None)
        if self._zoom_view is not None:
            try:
                self._zoom_view.zoom_changed.disconnect(self._on_zoom_changed)
            except (TypeError, RuntimeError):
                pass  # the view is gone, or was never connected
            self._zoom_view = None
        if self._selection_manager is not None:
            try:
                self._selection_manager.selection_changed.disconnect(self._on_selection_changed)
            except (TypeError, RuntimeError):
                pass
        if self._handles is not None:
            self._handles.remove_from_scene()
            self._handles = None
        super().deactivate()

    def cancel(self) -> None:
        self.leave_brush_edit()
        self.leave_point_edit()
        if self._rubber_band is not None and self._scene is not None:
            self._scene.removeItem(self._rubber_band)
            self._rubber_band = None
        self._state = _State.IDLE
        self._drag_items = []
        self._constrain_axis = None
        self._hide_readout()

    def _on_selection_changed(self, _items: list[object]) -> None:
        brush = self._brush_session
        if (
            brush is not None
            and self._selection_manager is not None
            and self._selection_manager.items != [brush.item]
        ):
            self.leave_brush_edit()
        session = self._point_session
        if (
            session is not None
            and self._selection_manager is not None
            and self._selection_manager.items != [session.item]
        ):
            self.leave_point_edit()
        self._update_handles()

    # --- point-editing mode (Basic Shape PRD 3.5, 4.5, 4.6, 7.5, 8.5, 9.7) ---

    @property
    def point_session(self) -> PointEditSession | None:
        """The point-editing session in progress, or None outside point-editing mode."""
        return self._point_session

    @property
    def point_handles(self) -> PointHandlesItem | None:
        return self._point_handles

    def enter_point_edit(self, item: SnapGraphicsItem) -> bool:
        """Enter point-editing mode on *item*; False when *item* has no points to edit."""
        if self._scene is None:
            return False
        session = session_for(item)
        if session is None:
            return False
        self.leave_point_edit()
        if self._selection_manager is not None and self._selection_manager.items != [item]:
            self._selection_manager.select(item)
        self._point_session = session
        self._point_handles = PointHandlesItem()
        self._scene.addItem(self._point_handles)
        self._scene.command_stack.stack_changed.connect(self._refresh_point_handles)
        self._refresh_point_handles()
        self._update_handles()
        self._show_status_hint()
        return True

    def handle_escape(self) -> bool:
        """Escape leaves brush editing or point-editing mode and keeps the selection
        (Blur PRD 2.8; Basic Shape PRD 3.5)."""
        return self.leave_brush_edit() or self.leave_point_edit()

    # --- brush-editing mode of a freeform blur region (Blur PRD 2.8) ---

    @property
    def brush_session(self) -> BlurBrushSession | None:
        """The brush-editing session in progress, or None outside brush-editing mode."""
        return self._brush_session

    def enter_brush_edit(self, item: SnapGraphicsItem) -> bool:
        """Enter brush editing on *item*; False unless it is a Freeform blur region."""
        if self._scene is None or not brush_editable(item):
            return False
        self.leave_point_edit()
        if self._selection_manager is not None and self._selection_manager.items != [item]:
            self._selection_manager.select(item)
        self._brush_session = BlurBrushSession(cast("BlurItem", item), self._brush_default())
        self._update_handles()
        self._show_status_hint()
        self._refresh_cursor()
        return True

    def _brush_default(self) -> float:
        """The Blur tool's Brush Size, so both brushes are the one size (2.6)."""
        view = self._view
        window = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        tool = manager.tool("blur") if manager is not None else None
        size = getattr(tool, "brush_size", None)
        return float(size) if isinstance(size, (int, float)) else DEFAULT_BLUR_BRUSH_SIZE

    def leave_brush_edit(self) -> bool:
        """Leave brush editing, undoing a stroke in progress; False when not in it."""
        session = self._brush_session
        if session is None:
            return False
        session.cancel_stroke()
        self._brush_session = None
        if self._state == _State.BRUSH_STROKE:
            self._state = _State.IDLE
        self._update_handles()
        self._show_status_hint()
        self._refresh_cursor()
        return True

    def _refresh_cursor(self) -> None:
        view = self._view
        if view is not None:
            view.set_hover_cursor(None if self._brush_session is None else self.cursor)

    def _brush_stroke_release(self) -> bool:
        session = self._brush_session
        self._state = _State.IDLE
        if session is not None:
            command = session.end_stroke()
            if command is not None and self._scene is not None:
                self._scene.command_stack.push(command)
        return True

    def leave_point_edit(self) -> bool:
        """Leave point-editing mode, undoing a drag in progress; False when not in it."""
        session = self._point_session
        if session is None:
            return False
        session.cancel_drag()
        self._point_session = None
        if self._state == _State.POINT_DRAG:
            self._state = _State.IDLE
        if self._scene is not None:
            try:
                self._scene.command_stack.stack_changed.disconnect(self._refresh_point_handles)
            except (TypeError, RuntimeError):
                pass
            if self._point_handles is not None and self._point_handles.scene() is not None:
                self._scene.removeItem(self._point_handles)
        self._point_handles = None
        self._update_handles()
        self._show_status_hint()
        return True

    def _refresh_point_handles(self) -> None:
        """Redraw the handles where the item's points now are (after a drag, undo, redo)."""
        session = self._point_session
        if session is None or self._point_handles is None:
            return
        if session.item.scene() is not self._scene:
            self.leave_point_edit()
            return
        self._point_handles.set_handles(session.handles(), session.guide_lines())

    def _point_drag_move(self, scene_pos: QPointF, event: QMouseEvent) -> bool:
        session = self._point_session
        if session is None or session.dragging is None:
            return True
        modifiers = event.modifiers()
        if not modifiers & Qt.KeyboardModifier.ShiftModifier:
            scene_pos = self._snap_pos(scene_pos)
        session.drag_to(session.dragging, scene_pos, modifiers)
        self._refresh_point_handles()
        return True

    def _point_drag_release(self) -> bool:
        session = self._point_session
        self._state = _State.IDLE
        if session is not None:
            command = session.end_drag()
            if command is not None and self._scene is not None:
                self._scene.command_stack.push(command)
            self._refresh_point_handles()
        return True

    def _update_handles(self) -> None:
        if self._handles is None or self._selection_manager is None:
            return
        if self._point_session is not None or self._brush_session is not None:
            # The item's own points, or the brush, replace the transform handles while
            # the mode lasts
            self._handles.remove_from_scene()
            return
        items = [i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)]
        if not items:
            self._handles.remove_from_scene()
            return
        self._handles.add_to_scene()
        rect = self._selection_bounding_rect(items)
        self._handles.update_rect(rect)

    def _selection_bounding_rect(self, items: list[SnapGraphicsItem]) -> QRectF:
        if not items:
            return QRectF()
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        return rect

    def _scene_pos(self, event: QMouseEvent) -> QPointF | None:
        view = self._view
        if view is not None:
            return view.mapToScene(event.pos())
        return None

    @staticmethod
    def _top_level(item: SnapGraphicsItem) -> SnapGraphicsItem:
        """The item itself, or the outermost group holding it.

        A group's members are its child items (General UI PRD 3.6); a click or a rubber
        band on a member selects the group, never the member.
        """
        parent = item.parentItem()
        while isinstance(parent, SnapGraphicsItem):
            item = parent
            parent = item.parentItem()
        return item

    def _item_at(self, scene_pos: QPointF) -> SnapGraphicsItem | None:
        if self._scene is None:
            return None
        view = self._view
        if view is None:
            return None
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, SnapGraphicsItem):
                item = self._top_level(gitem)
                # Skip items on locked/hidden layers
                layer = self._scene.layer_manager.layer_by_id(item.layer_id)
                if layer is not None and (layer.locked or not layer.visible):
                    continue
                return item
        return None

    def _locked_item_at(self, scene_pos: QPointF) -> bool:
        """Whether a visible item on a locked layer is under *scene_pos*."""
        if self._scene is None:
            return False
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, SnapGraphicsItem):
                item = self._top_level(gitem)
                layer = self._scene.layer_manager.layer_by_id(item.layer_id)
                if layer is not None and layer.locked and layer.visible:
                    return True
        return False

    def _update_hover_cursor(self, scene_pos: QPointF) -> None:
        """The idle cursor of PRD 6.6.

        Open hand over what can be dragged, forbidden over a locked layer's item,
        the handle's own cursor over a handle, the arrow elsewhere.
        """
        view = self._view
        if view is None:
            return
        if self._point_session is not None and self._point_session.handle_at(scene_pos):
            view.set_hover_cursor(Qt.CursorShape.SizeAllCursor)
            return
        if self._handles is not None and self._handles.scene() is not None:
            handle = self._handles.handle_at(scene_pos)
            if handle is not None:
                view.set_hover_cursor(self._handles.cursor_for(handle))
                return
        if self._item_at(scene_pos) is not None:
            view.set_hover_cursor(Qt.CursorShape.OpenHandCursor)
        elif (
            self._handles is not None
            and self._handles.scene() is not None
            and self._handles.current_rect.contains(scene_pos)
        ):
            view.set_hover_cursor(Qt.CursorShape.OpenHandCursor)
        elif self._locked_item_at(scene_pos):
            view.set_hover_cursor(Qt.CursorShape.ForbiddenCursor)
        else:
            view.set_hover_cursor(None)

    # --- mouse events ---

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or self._selection_manager is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        scene_pos = self._scene_pos(event)
        if scene_pos is None:
            return False

        self._press_pos = scene_pos
        self._drag_total = QPointF(0, 0)
        self._constrain_axis = None
        self._group_hint = False

        # Brush-editing mode: every press paints and Alt+press erases, wherever it lands,
        # since painting past the region is how the region grows; only Enter, Escape, a
        # tool switch, or a new selection leave the mode (Blur PRD 2.8)
        brush = self._brush_session
        if brush is not None:
            erase = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            brush.begin_stroke(scene_pos, erase=erase)
            self._state = _State.BRUSH_STROKE
            return True

        # Point-editing mode: a handle starts a point drag, a press on the item keeps the
        # mode, and a press anywhere else leaves it and is handled as usual (PRD 3.5)
        session = self._point_session
        if session is not None:
            key = session.handle_at(scene_pos)
            if key is not None:
                session.begin_drag(key)
                self._state = _State.POINT_DRAG
                return True
            if self._item_at(scene_pos) is session.item:
                return True
            self.leave_point_edit()

        # Check if clicking on a transform handle (only while the handles are shown)
        if self._handles is not None and self._handles.scene() is not None:
            handle = self._handles.handle_at(scene_pos)
            if handle is not None:
                self._state = _State.HANDLE_DRAG
                self._drag_start = scene_pos
                self._handle_pos = handle
                self._handle_origin_rect = QRectF(self._handles.current_rect)
                self._handle_anchor = self._handles.anchor_for_handle(handle)
                # Save original pos/transform for each selected item
                items = [
                    i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)
                ]
                self._handle_item_originals = [
                    (item, QPointF(item.pos()), QTransform(item.transform())) for item in items
                ]
                # Save original geometry for text items so resize reflows text
                self._text_originals = {}
                for it in items:
                    if isinstance(it, TextItem):
                        self._text_originals[id(it)] = {
                            "width": it._width,
                            "height": it._height,
                            "frame_height": it._frame_height(),
                            "auto_size": it._auto_size,
                            "font_size": it.text_document.defaultFont().pointSize(),
                        }
                    elif isinstance(it, CalloutItem):
                        self._text_originals[id(it)] = {
                            "rect": QRectF(it._rect),
                            "tail": QPointF(it._tail_tip),
                            "font_size": it.text_document.defaultFont().pointSize(),
                        }
                return True

        # Check for item under cursor
        item = self._item_at(scene_pos)

        # If no item's shape was hit but the click is inside the selection bounding
        # rect (where handles are drawn), allow drag of the current selection.
        # This is essential for text items with transparent bg/no border whose
        # shape() only covers the text content area, not the full frame.
        if item is None and self._handles is not None and self._selection_manager is not None:
            sel_rect = self._handles.current_rect
            if not sel_rect.isEmpty() and sel_rect.contains(scene_pos):
                self._drag_start = scene_pos
                self._drag_items = [
                    i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)
                ]
                if self._drag_items:
                    self._state = _State.DRAGGING
                    self._set_cursor(Qt.CursorShape.ClosedHandCursor)
                    return True

        if item is not None:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if ctrl:
                self._selection_manager.toggle(item)
            elif shift:
                self._selection_manager.select(item, add=True)
            elif item not in self._selection_manager.items:
                self._selection_manager.select(item)
            # Prepare for drag
            self._drag_start = scene_pos
            self._drag_items = [
                i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)
            ]
            self._state = _State.DRAGGING
            self._set_cursor(Qt.CursorShape.ClosedHandCursor)
        else:
            # No item — start rubber-band or deselect
            if not (
                event.modifiers()
                & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
            ):
                self._selection_manager.deselect_all()
            self._drag_start = scene_pos
            self._state = _State.RUBBER_BAND
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._scene is None:
            return False
        scene_pos = self._scene_pos(event)
        if scene_pos is None:
            return False

        if self._state == _State.DRAGGING:
            return self._handle_drag_move(scene_pos, event)
        elif self._state == _State.RUBBER_BAND:
            return self._handle_rubber_band_move(scene_pos)
        elif self._state == _State.HANDLE_DRAG:
            return self._handle_transform_move(scene_pos, event)
        elif self._state == _State.POINT_DRAG:
            return self._point_drag_move(scene_pos, event)
        elif self._state == _State.BRUSH_STROKE:
            if self._brush_session is not None:
                self._brush_session.stroke_to(scene_pos)
            return True
        if self._brush_session is not None:
            self._refresh_cursor()
            return False
        self._update_hover_cursor(scene_pos)
        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._scene is None:
            return False
        scene_pos = self._scene_pos(event)
        if scene_pos is None:
            self._state = _State.IDLE
            return False

        if self._state == _State.DRAGGING:
            handled = self._handle_drag_release()
            self._update_hover_cursor(scene_pos)
            return handled
        elif self._state == _State.RUBBER_BAND:
            return self._handle_rubber_band_release(scene_pos, event)
        elif self._state == _State.HANDLE_DRAG:
            return self._handle_transform_release()
        elif self._state == _State.POINT_DRAG:
            return self._point_drag_release()
        elif self._state == _State.BRUSH_STROKE:
            return self._brush_stroke_release()

        self._state = _State.IDLE
        return True

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        if self._scene is None or self._selection_manager is None:
            return False
        scene_pos = self._scene_pos(event)
        if scene_pos is None:
            return False

        item = self._item_at(scene_pos)
        if self._brush_session is not None:
            return True  # the second press of the double-click already painted
        session = self._point_session
        if session is not None and (item is session.item or session.handle_at(scene_pos)):
            # A double-click on the item in point-editing mode inserts a point (9.7, 8.5)
            command = session.double_click(scene_pos)
            if command is not None:
                self._scene.command_stack.push(command)
            return True
        if item is not None:
            self._selection_manager.select(item)
            if isinstance(item, GroupItem):
                # A group's members are edited after Ungroup (kickoff silence 1); the
                # status bar says so.
                self._group_hint = True
                self._show_status_hint()
                return True
            # Double-click on text/callout: switch to text tool
            if isinstance(item, (TextItem, CalloutItem)):
                view = self._view
                if view is not None:
                    parent = view.parentWidget()
                    if parent is not None and hasattr(parent, "tool_manager"):
                        parent.tool_manager.activate("text")
                return True
            # Double-click on a marker item: its editor (Numbered Steps PRD 2.8; kickoff
            # silence 9), through the window so the placing tool shares the route
            if isinstance(item, NumberedStepItem | StampItem | EmojiItem):
                view = self._view
                window = view.window() if view is not None else None
                open_editor = getattr(window, "open_marker_editor", None)
                if callable(open_editor):
                    open_editor(item)
                return True
            # A Freeform blur region: brush-editing mode (Blur PRD 2.8); a rectangular or
            # elliptical one has no mask to paint and nothing happens
            if isinstance(item, BlurItem):
                self.enter_brush_edit(item)
                return True
            # A line, an arrow, an arc, a polygon, or a freehand item: point-editing mode
            # (Basic Shape PRD 3.5; Basic Shape remainder decision 1, option A)
            self.enter_point_edit(item)
            return True

        # Double-click on empty canvas: toggle fit/100%
        view = self._view
        if view is not None:
            if view.zoom_percent == 100:
                view.fit_in_view_all()
            else:
                view.set_zoom(100)
        return True

    def _show_status_hint(self) -> None:
        """Push the current hint to the main window's status bar, when there is one."""
        view = self._view
        window = view.window() if view is not None else None
        show = getattr(window, "show_status_hint", None)
        if callable(show):
            show(self.status_hint)

    # --- drag movement ---

    def _handle_drag_move(self, scene_pos: QPointF, event: QMouseEvent) -> bool:
        """Move the dragged items so their total displacement follows the pointer.

        Everything is computed from the whole movement since the press, never from one
        event's increment: with Snap to Grid on, the increment was once rounded to the
        grid on its own and the remainder thrown away, so a pointer moving a few pixels
        per event moved nothing at all and a flick jumped a grid step (end-to-end pass
        finding 3). With Snap to Grid the selection frame's top-left corner lands on the
        grid; the items are moved by the difference from what has been applied so far.
        """
        raw_total = scene_pos - self._press_pos

        # Check if we've passed the drag threshold
        if abs(raw_total.x()) < DRAG_THRESHOLD and abs(raw_total.y()) < DRAG_THRESHOLD:
            return True

        # Shift constrains to dominant axis
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            if self._constrain_axis is None and (
                abs(raw_total.x()) > 10 or abs(raw_total.y()) > 10
            ):
                self._constrain_axis = "x" if abs(raw_total.x()) >= abs(raw_total.y()) else "y"
            if self._constrain_axis == "x":
                raw_total = QPointF(raw_total.x(), 0)
            elif self._constrain_axis == "y":
                raw_total = QPointF(0, raw_total.y())
        else:
            self._constrain_axis = None

        target = QPointF(raw_total)
        view = self._view
        at_rest = self._selection_bounding_rect(self._drag_items).translated(
            -self._drag_total.x(), -self._drag_total.y()
        )
        # View > Snap to Grid: the selection frame's top-left corner lands on the grid
        # line nearest where the pointer has carried it (end-to-end pass decision 5,
        # option B: the item lands on the grid wherever it started, as guides work)
        if view is not None and view.snap_to_grid:
            grid = view._grid_size  # noqa: SLF001
            corner = at_rest.topLeft() + raw_total
            target = QPointF(
                round(corner.x() / grid) * grid - at_rest.left(),
                round(corner.y() / grid) * grid - at_rest.top(),
            )
        # View > Snap to Guides: an edge or the centre of the selection lands on a guide
        if view is not None and view.snap_to_guides:
            target += view.snap_rect_offset(at_rest.translated(target))

        delta = target - self._drag_total
        if delta.x() != 0 or delta.y() != 0:
            for item in self._drag_items:
                item.moveBy(delta.x(), delta.y())
            self._drag_total = QPointF(target)
            self._update_handles()

        # The ΔX / ΔY readout, on the widget over the viewport the drawing tools use, and
        # never a Qt tooltip window: on Linux the tooltip took the view's focus and a
        # repaint on every move, and the drag jumped (Technical Architecture PRD 3.4;
        # end-to-end pass finding 3)
        if view is not None:
            viewport = view.viewport()
            if viewport is not None:
                dx = self._drag_total.x()
                dy = self._drag_total.y()
                dimension_overlay(viewport).show_measurement(
                    event.pos(), f"\u0394X: {dx:+.0f}  \u0394Y: {dy:+.0f}", False, None
                )
        return True

    def _show_readout(self, cursor: QPointF, text: str) -> None:
        """Put *text* beside the cursor at scene position *cursor*, on the widget over the
        viewport the drawing tools use (the rotate and resize readouts; the move readout
        is placed from its event above)."""
        view = self._view
        viewport = view.viewport() if view is not None else None
        if view is None or viewport is None:
            return
        dimension_overlay(viewport).show_measurement(view.mapFromScene(cursor), text, False, None)

    def _hide_readout(self) -> None:
        """Take the drag readout down: the drag is over or cancelled."""
        view = self._view
        viewport = view.viewport() if view is not None else None
        overlay = existing_dimension_overlay(viewport) if viewport is not None else None
        if overlay is not None:
            overlay.hide_feedback()

    def _set_cursor(self, cursor: Qt.CursorShape) -> None:
        view = self._view
        if view is not None:
            view.set_hover_cursor(cursor)

    def _handle_drag_release(self) -> bool:
        total = self._drag_total
        if self._drag_items and (
            abs(total.x()) >= DRAG_THRESHOLD or abs(total.y()) >= DRAG_THRESHOLD
        ):
            # We already moved items visually. Undo that, then push command.
            for item in self._drag_items:
                item.moveBy(-total.x(), -total.y())
            cmd = MoveItemsCommand(self._drag_items, total)
            if self._scene is not None:
                self._scene.command_stack.push(cmd)
        self._state = _State.IDLE
        self._drag_items = []
        self._constrain_axis = None
        self._hide_readout()
        self._update_handles()
        return True

    # --- rubber-band ---

    def _handle_rubber_band_move(self, scene_pos: QPointF) -> bool:
        delta = scene_pos - self._drag_start
        if abs(delta.x()) < DRAG_THRESHOLD and abs(delta.y()) < DRAG_THRESHOLD:
            return True

        rect = QRectF(self._drag_start, scene_pos).normalized()
        if self._rubber_band is None and self._scene is not None:
            self._rubber_band = QGraphicsRectItem(rect)
            self._rubber_band.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
            self._rubber_band.setBrush(QBrush(QColor(0, 120, 215, 30)))
            self._rubber_band.setZValue(999999)
            self._scene.addItem(self._rubber_band)
        elif self._rubber_band is not None:
            self._rubber_band.setRect(rect)
        return True

    def _handle_rubber_band_release(self, scene_pos: QPointF, event: QMouseEvent) -> bool:
        rect = QRectF(self._drag_start, scene_pos).normalized()

        # Remove rubber band visual
        if self._rubber_band is not None and self._scene is not None:
            self._scene.removeItem(self._rubber_band)
            self._rubber_band = None

        if self._selection_manager is None or self._scene is None:
            self._state = _State.IDLE
            return True

        # If the rect is too small, treat as a click (deselect already happened)
        if rect.width() < DRAG_THRESHOLD and rect.height() < DRAG_THRESHOLD:
            self._state = _State.IDLE
            return True

        # Find items in the rubber-band rectangle; a member counts as its group, once
        found: dict[SnapGraphicsItem, None] = {}
        for gitem in self._scene.items(rect, Qt.ItemSelectionMode.IntersectsItemShape):
            if isinstance(gitem, SnapGraphicsItem):
                item = self._top_level(gitem)
                layer = self._scene.layer_manager.layer_by_id(item.layer_id)
                if layer is not None and (layer.locked or not layer.visible):
                    continue
                found[item] = None
        items_in_rect: list[SnapGraphicsItem] = list(found)

        # Modifier logic
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if ctrl:
            # Toggle (XOR)
            for item in items_in_rect:
                self._selection_manager.toggle(item)
        elif shift:
            # Additive (union)
            for item in items_in_rect:
                if item not in self._selection_manager.items:
                    self._selection_manager.select(item, add=True)
        else:
            # Replace selection
            from PyQt6.QtWidgets import QGraphicsItem

            gi_items: list[QGraphicsItem] = list(items_in_rect)
            self._selection_manager.select_items(gi_items)

        self._state = _State.IDLE
        self._update_handles()
        return True

    # --- handle transform ---

    def _handle_transform_move(self, scene_pos: QPointF, event: QMouseEvent) -> bool:
        if self._handle_pos is None or not self._handle_item_originals:
            return True

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if self._handle_pos == HandlePosition.ROTATE:
            self._apply_rotation(scene_pos, shift)
            self._update_handles()
            return True
        scene_pos = self._snap_pos(scene_pos)
        if self._handle_pos in CORNER_HANDLES:
            self._apply_corner_resize(scene_pos, shift, alt)
        elif self._handle_pos in EDGE_HANDLES:
            self._apply_edge_resize(scene_pos, ctrl, shift)

        self._update_handles()
        return True

    def _apply_rotation(self, cursor: QPointF, snap: bool) -> None:
        """Rotate all selected items around the selection center."""
        center = self._handle_origin_rect.center()
        angle = math.degrees(
            math.atan2(cursor.y() - center.y(), cursor.x() - center.x())
        ) - math.degrees(
            math.atan2(
                self._drag_start.y() - center.y(),
                self._drag_start.x() - center.x(),
            )
        )
        if snap:
            angle = round(angle / 15.0) * 15.0

        for item, orig_pos, orig_xform in self._handle_item_originals:
            # Rotate position around center
            offset = orig_pos - center
            rad = math.radians(angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            new_offset = QPointF(
                offset.x() * cos_a - offset.y() * sin_a,
                offset.x() * sin_a + offset.y() * cos_a,
            )
            item.setPos(center + new_offset)
            # Apply rotation transform
            xform = QTransform(orig_xform)
            xform.rotate(angle)
            item.setTransform(xform)

        self._show_readout(cursor, f"{angle:+.1f}°")

    def _apply_corner_resize(self, cursor: QPointF, proportional: bool, from_center: bool) -> None:
        """Resize from a corner handle."""
        anchor = self._handle_origin_rect.center() if from_center else self._handle_anchor
        orig_rect = self._handle_origin_rect

        # Compute scale factors relative to anchor
        orig_w = abs(self._drag_start.x() - anchor.x())
        orig_h = abs(self._drag_start.y() - anchor.y())
        new_w = abs(cursor.x() - anchor.x())
        new_h = abs(cursor.y() - anchor.y())

        sx = new_w / max(orig_w, 1.0)
        sy = new_h / max(orig_h, 1.0)

        if proportional:
            s = min(sx, sy)
            sx = sy = s

        # Clamp minimum
        sx = max(sx, 0.01)
        sy = max(sy, 0.01)

        for item, orig_pos, orig_xform in self._handle_item_originals:
            offset = orig_pos - anchor
            item.setPos(anchor + QPointF(offset.x() * sx, offset.y() * sy))
            if id(item) in self._text_originals:
                self._apply_text_resize(item, sx, sy, orig_xform, scale_font=proportional)
            else:
                xform = QTransform(orig_xform)
                xform.scale(sx, sy)
                item.setTransform(xform)

        new_rect_w = orig_rect.width() * sx
        new_rect_h = orig_rect.height() * sy
        self._show_readout(cursor, f"{new_rect_w:.0f} × {new_rect_h:.0f}")

    def _apply_edge_resize(self, cursor: QPointF, skew: bool, shift: bool = False) -> None:
        """Resize from an edge midpoint handle. Ctrl = shear."""
        anchor = self._handle_anchor
        orig_rect = self._handle_origin_rect

        if skew:
            self._apply_skew(cursor)
            return

        hp = self._handle_pos
        sx = 1.0
        sy = 1.0
        if hp in (HandlePosition.MIDDLE_LEFT, HandlePosition.MIDDLE_RIGHT):
            orig_w = abs(self._drag_start.x() - anchor.x())
            new_w = abs(cursor.x() - anchor.x())
            sx = max(new_w / max(orig_w, 1.0), 0.01)
        elif hp in (HandlePosition.TOP_CENTER, HandlePosition.BOTTOM_CENTER):
            orig_h = abs(self._drag_start.y() - anchor.y())
            new_h = abs(cursor.y() - anchor.y())
            sy = max(new_h / max(orig_h, 1.0), 0.01)

        for item, orig_pos, orig_xform in self._handle_item_originals:
            offset = orig_pos - anchor
            item.setPos(anchor + QPointF(offset.x() * sx, offset.y() * sy))
            if id(item) in self._text_originals:
                self._apply_text_resize(item, sx, sy, orig_xform, scale_font=shift)
            else:
                xform = QTransform(orig_xform)
                xform.scale(sx, sy)
                item.setTransform(xform)

        new_w = orig_rect.width() * sx
        new_h = orig_rect.height() * sy
        self._show_readout(cursor, f"{new_w:.0f} × {new_h:.0f}")

    def _apply_skew(self, cursor: QPointF) -> None:
        """Apply shear when Ctrl+edge drag."""
        hp = self._handle_pos
        delta = cursor - self._drag_start
        rect = self._handle_origin_rect

        shear_x = 0.0
        shear_y = 0.0
        if hp in (HandlePosition.TOP_CENTER, HandlePosition.BOTTOM_CENTER):
            shear_x = delta.x() / max(rect.height(), 1.0)
        elif hp in (HandlePosition.MIDDLE_LEFT, HandlePosition.MIDDLE_RIGHT):
            shear_y = delta.y() / max(rect.width(), 1.0)

        center = rect.center()
        for item, orig_pos, orig_xform in self._handle_item_originals:
            offset = orig_pos - center
            new_x = offset.x() + offset.y() * shear_x
            new_y = offset.y() + offset.x() * shear_y
            item.setPos(center + QPointF(new_x, new_y))
            xform = QTransform(orig_xform)
            xform.shear(shear_x, shear_y)
            item.setTransform(xform)

    def _apply_text_resize(
        self,
        item: SnapGraphicsItem,
        sx: float,
        sy: float,
        orig_xform: QTransform,
        *,
        scale_font: bool = False,
    ) -> None:
        """Resize a text item.

        scale_font=False (default): reflow — change box width, keep font size.
        scale_font=True (Shift held): scale — apply visual transform so text
        scales proportionally; font size is updated on release.
        """
        orig = self._text_originals.get(id(item))
        if orig is None:
            return

        if scale_font:
            # Scale mode: reset geometry to original, apply visual transform
            item.prepareGeometryChange()
            if isinstance(item, TextItem):
                item._width = orig["width"]  # noqa: SLF001
            elif isinstance(item, CalloutItem):
                item._rect = QRectF(orig["rect"])  # noqa: SLF001
                item._tail_tip = QPointF(orig["tail"])  # noqa: SLF001
            xform = QTransform(orig_xform)
            xform.scale(sx, sy)
            item.setTransform(xform)
        else:
            # Reflow mode: change geometry, keep original transform
            item.prepareGeometryChange()
            if isinstance(item, TextItem):
                item._width = max(20.0, orig["width"] * sx)  # noqa: SLF001
                # Handle vertical resize: disable auto_size and set explicit height
                if sy != 1.0:
                    new_h = max(MIN_TEXT_BOX_HEIGHT, orig["frame_height"] * sy)
                    item._auto_size = False  # noqa: SLF001
                    item._height = new_h  # noqa: SLF001
            elif isinstance(item, CalloutItem):
                orig_rect: QRectF = orig["rect"]
                orig_tail: QPointF = orig["tail"]
                item._rect = QRectF(  # noqa: SLF001
                    orig_rect.x() * sx,
                    orig_rect.y() * sy,
                    orig_rect.width() * sx,
                    orig_rect.height() * sy,
                )
                item._tail_tip = QPointF(  # noqa: SLF001
                    orig_tail.x() * sx, orig_tail.y() * sy
                )
            item.setTransform(orig_xform)

    def _handle_transform_release(self) -> bool:
        """Commit transform as undoable command(s)."""
        from snapmock.commands.macro_command import MacroCommand
        from snapmock.commands.transform_item import TransformItemCommand

        self._hide_readout()
        commands: list[Any] = []
        for item, orig_pos, orig_xform in self._handle_item_originals:
            new_pos = QPointF(item.pos())
            new_xform = QTransform(item.transform())

            orig = self._text_originals.get(id(item))
            if orig is not None:
                # Determine mode: if transform changed → scale mode, else reflow
                scale_mode = new_xform != orig_xform
                sub: list[Any] = []

                if scale_mode:
                    # Shift was held: convert visual scale to font + geometry change
                    sub.extend(
                        self._commit_text_scale(
                            item, orig, orig_pos, new_pos, orig_xform, new_xform
                        )
                    )
                else:
                    # Normal resize: commit the geometry (width/rect) change
                    sub.extend(self._commit_text_reflow(item, orig, orig_pos, new_pos, orig_xform))

                if sub:
                    commands.extend(sub)
            elif new_pos != orig_pos or new_xform != orig_xform:
                # Non-text items: standard visual transform
                item.setPos(orig_pos)
                item.setTransform(orig_xform)
                commands.append(
                    TransformItemCommand(item, orig_pos, new_pos, orig_xform, new_xform)
                )

        if commands and self._scene is not None:
            if len(commands) == 1:
                self._scene.command_stack.push(commands[0])
            else:
                self._scene.command_stack.push(MacroCommand(commands, "Resize items"))

        self._state = _State.IDLE
        self._handle_pos = None
        self._handle_item_originals = []
        self._text_originals = {}
        self._update_handles()
        return True

    def _commit_text_reflow(
        self,
        item: SnapGraphicsItem,
        orig: dict[str, Any],
        orig_pos: QPointF,
        new_pos: QPointF,
        orig_xform: QTransform,
    ) -> list[Any]:
        """Commit a reflow resize: width/rect changed, font unchanged."""
        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.commands.transform_item import TransformItemCommand

        sub: list[Any] = []
        if isinstance(item, TextItem):
            new_width = item._width  # noqa: SLF001
            new_auto_size = item._auto_size  # noqa: SLF001
            new_height = item._height  # noqa: SLF001
            old_width: float = orig["width"]
            old_auto_size: bool = orig["auto_size"]
            old_height = orig["height"]
            # Revert to original state
            item.setPos(orig_pos)
            item.prepareGeometryChange()
            item._width = old_width  # noqa: SLF001
            item._auto_size = old_auto_size  # noqa: SLF001
            item._height = old_height  # noqa: SLF001
            if new_pos != orig_pos:
                sub.append(TransformItemCommand(item, orig_pos, new_pos, orig_xform, orig_xform))
            if new_width != old_width:
                sub.append(ModifyPropertyCommand(item, "text_width", old_width, new_width))
            if new_auto_size != old_auto_size:
                sub.append(ModifyPropertyCommand(item, "auto_size", old_auto_size, new_auto_size))
            if new_height != old_height:
                sub.append(ModifyPropertyCommand(item, "text_height", old_height, new_height))
        elif isinstance(item, CalloutItem):
            new_rect = QRectF(item._rect)  # noqa: SLF001
            new_tail = QPointF(item._tail_tip)  # noqa: SLF001
            old_rect: QRectF = orig["rect"]
            old_tail: QPointF = orig["tail"]
            item.setPos(orig_pos)
            item.box_rect = QRectF(old_rect)
            item.tail_tip = QPointF(old_tail)
            if new_pos != orig_pos:
                sub.append(TransformItemCommand(item, orig_pos, new_pos, orig_xform, orig_xform))
            if new_rect != old_rect:
                sub.append(
                    ModifyPropertyCommand(item, "box_rect", QRectF(old_rect), QRectF(new_rect))
                )
            if new_tail != old_tail:
                sub.append(
                    ModifyPropertyCommand(item, "tail_tip", QPointF(old_tail), QPointF(new_tail))
                )
        return sub

    def _commit_text_scale(
        self,
        item: SnapGraphicsItem,
        orig: dict[str, Any],
        orig_pos: QPointF,
        new_pos: QPointF,
        orig_xform: QTransform,
        new_xform: QTransform,
    ) -> list[Any]:
        """Commit a scale resize: convert visual transform to font + geometry change."""
        from PyQt6.QtGui import QFont

        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.commands.transform_item import TransformItemCommand

        # Extract relative scale factors from the transform
        inv, ok = orig_xform.inverted()
        if ok:
            relative = inv * new_xform
            sx = relative.m11()
            sy = relative.m22()
        else:
            sx = sy = 1.0

        old_font_size: int = orig["font_size"]
        avg = (abs(sx) + abs(sy)) / 2.0
        new_font_size = max(1, int(old_font_size * avg))

        sub: list[Any] = []

        # Revert item to original state (remove visual transform)
        item.setPos(orig_pos)
        item.setTransform(orig_xform)

        if isinstance(item, TextItem):
            old_width: float = orig["width"]
            new_width = max(20.0, old_width * abs(sx))
            item.prepareGeometryChange()
            item._width = old_width  # noqa: SLF001
            doc_font = item.text_document.defaultFont()
            doc_font.setPointSize(old_font_size)
            item.text_document.setDefaultFont(doc_font)
            if new_pos != orig_pos:
                sub.append(TransformItemCommand(item, orig_pos, new_pos, orig_xform, orig_xform))
            if new_width != old_width:
                sub.append(ModifyPropertyCommand(item, "text_width", old_width, new_width))
            if new_font_size != old_font_size:
                old_font = QFont(item.text_document.defaultFont())
                new_font = QFont(item.text_document.defaultFont())
                new_font.setPointSize(new_font_size)
                sub.append(ModifyPropertyCommand(item, "font", old_font, new_font))

        elif isinstance(item, CalloutItem):
            old_rect: QRectF = orig["rect"]
            old_tail: QPointF = orig["tail"]
            new_rect = QRectF(
                old_rect.x() * abs(sx),
                old_rect.y() * abs(sy),
                old_rect.width() * abs(sx),
                old_rect.height() * abs(sy),
            )
            new_tail = QPointF(old_tail.x() * abs(sx), old_tail.y() * abs(sy))
            item.box_rect = QRectF(old_rect)
            item.tail_tip = QPointF(old_tail)
            doc_font = item.text_document.defaultFont()
            doc_font.setPointSize(old_font_size)
            item.text_document.setDefaultFont(doc_font)
            if new_pos != orig_pos:
                sub.append(TransformItemCommand(item, orig_pos, new_pos, orig_xform, orig_xform))
            if new_rect != old_rect:
                sub.append(
                    ModifyPropertyCommand(item, "box_rect", QRectF(old_rect), QRectF(new_rect))
                )
            if new_tail != old_tail:
                sub.append(
                    ModifyPropertyCommand(item, "tail_tip", QPointF(old_tail), QPointF(new_tail))
                )
            if new_font_size != old_font_size:
                old_font = QFont(item.text_document.defaultFont())
                new_font = QFont(item.text_document.defaultFont())
                new_font.setPointSize(new_font_size)
                sub.append(ModifyPropertyCommand(item, "font", old_font, new_font))

        return sub

    # --- key events ---

    def key_press(self, event: QKeyEvent) -> bool:
        if self._selection_manager is None or self._scene is None:
            return False

        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Enter and Escape leave brush-editing mode (Blur PRD 2.8); Escape also leaves
        # point-editing mode and keeps the selection (Basic Shape PRD 3.5)
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.leave_brush_edit():
                return True
        if key == Qt.Key.Key_Escape and self.leave_point_edit():
            return True

        # Arrow key nudge: one pixel, or one grid step with Shift (Doug's decision of
        # 09-15-26, end-to-end pass finding 4: the grid step, where the PRDs said 10 px)
        view = self._view
        grid = view._grid_size if view is not None else GRID_SIZE_DEFAULT  # noqa: SLF001
        nudge = grid if shift else 1
        delta: QPointF | None = None

        if key == Qt.Key.Key_Left:
            delta = QPointF(-nudge, 0)
        elif key == Qt.Key.Key_Right:
            delta = QPointF(nudge, 0)
        elif key == Qt.Key.Key_Up:
            delta = QPointF(0, -nudge)
        elif key == Qt.Key.Key_Down:
            delta = QPointF(0, nudge)

        if delta is not None:
            items = [i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)]
            if items:
                cmd = MoveItemsCommand(items, delta)
                self._scene.command_stack.push(cmd)
                self._update_handles()
                return True
            # No items selected — let the event fall through for viewport pan
            return False

        # Delete / Backspace
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            items = [i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)]
            if items:
                self._delete_items(items)
            return True

        # Tab / Shift+Tab cycle the selection through the active layer (General UI PRD 12.3)
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            return self.cycle_selection(forward=key == Qt.Key.Key_Tab and not shift)

        return False

    def cycle_selection(self, *, forward: bool = True) -> bool:
        """Select the next (or previous) item on the active layer in z-order.

        Returns False when the layer has no selectable items.
        """
        if self._scene is None or self._selection_manager is None:
            return False
        active = self._scene.layer_manager.active_layer
        if active is None:
            return False
        order = {item_id: n for n, item_id in enumerate(active.item_ids)}
        # Top-level items only: a group is one stop and its members are none
        candidates = sorted(
            (i for i in self._scene.annotation_items() if i.layer_id == active.layer_id),
            key=lambda i: (order.get(i.item_id, len(order)), i.zValue()),
        )
        if not candidates:
            return False
        current = [i for i in candidates if i in self._selection_manager.items]
        if current:
            index = candidates.index(current[-1] if forward else current[0])
            index = (index + 1) % len(candidates) if forward else (index - 1) % len(candidates)
        else:
            index = 0 if forward else len(candidates) - 1
        self._selection_manager.select(candidates[index])
        self._update_handles()
        return True

    def _delete_items(self, items: list[SnapGraphicsItem]) -> None:
        if self._scene is None or self._selection_manager is None:
            return
        from snapmock.commands.remove_item import RemoveItemCommand

        # Skip items on locked layers
        deletable = []
        for item in items:
            layer = self._scene.layer_manager.layer_by_id(item.layer_id)
            if layer is not None and layer.locked:
                continue
            deletable.append(item)

        for item in deletable:
            self._scene.command_stack.push(RemoveItemCommand(self._scene, item))
        self._selection_manager.deselect_all()

    @property
    def status_hint(self) -> str:
        if self._brush_session is not None:
            return self._brush_session.status_hint
        if self._point_session is not None:
            return self._point_session.status_hint
        if self._state == _State.DRAGGING:
            return "Shift: constrain axis | Release to place"
        if self._state == _State.RUBBER_BAND:
            return "Shift: add to selection | Ctrl: toggle selection"
        if self._state == _State.HANDLE_DRAG:
            if self._handle_pos == HandlePosition.ROTATE:
                return "Shift: snap to 15° increments"
            if self._text_originals:
                return "Shift: scale text | Alt: from center"
            return "Shift: proportional | Alt: from center | Ctrl+edge: skew"
        if self._group_hint:
            return "Group selected | Ungroup (Ctrl+Shift+G) to edit its items"
        return "Click to select | Drag to move | Shift+click: add | Right-click: menu"

    # --- context menu ---

    def context_menu(self, event: object) -> bool:
        from PyQt6.QtGui import QContextMenuEvent

        if not isinstance(event, QContextMenuEvent):
            return False
        if self._scene is None or self._selection_manager is None:
            return False

        view = self._view
        if view is None:
            return False

        scene_pos = view.mapToScene(event.pos())
        # In point-editing mode a right-click on a handle deletes that point (9.7, 8.5)
        # rather than opening the menu, even where the minimum refuses the deletion
        session = self._point_session
        if session is not None and session.handle_at(scene_pos) is not None:
            command = session.right_click(scene_pos)
            if command is not None:
                self._scene.command_stack.push(command)
            return True
        # The view now lives inside the document tab stack, so its direct parent is a
        # QStackedWidget; the context-menu builders need the MainWindow.
        parent = view.window()
        if parent is None or not hasattr(parent, "selection_manager"):
            return False

        # If right-click on an unselected item, select it first
        item = self._item_at(scene_pos)
        if item is not None and item not in self._selection_manager.items:
            self._selection_manager.select(item)

        from snapmock.ui.context_menus import build_canvas_context_menu, build_item_context_menu

        if item is not None:
            menu = build_item_context_menu(parent)  # type: ignore[arg-type]
        else:
            menu = build_canvas_context_menu(parent)  # type: ignore[arg-type]

        menu.exec(event.globalPos())
        return True
