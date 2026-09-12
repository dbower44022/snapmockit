"""LineTool — click-and-drag to create lines."""

from __future__ import annotations

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
)
from snapmock.core.path_utils import constrain_angle
from snapmock.items.line_item import LineItem
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.dimension_overlay import length_angle_text


class LineTool(BaseTool):
    """Interactive tool for creating lines by click-and-drag."""

    # Tool Options Bar shared controls (General UI PRD 5.3)
    options_controls = (
        "stroke_color",
        "stroke_width",
        "stroke_style",
        "stroke_opacity",
        "shadow_enabled",
    )

    def __init__(self) -> None:
        super().__init__()
        self._start: QPointF = QPointF()
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
        }

    @property
    def tool_id(self) -> str:
        return "line"

    @property
    def display_name(self) -> str:
        return "Line"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def status_hint(self) -> str:
        """3.7's Idle and Drawing rows; the Drawing row's values are the tooltip's."""
        if self._item is not None:
            measurement = " | ".join(self.drawing_measurement)
            return f"{measurement} | Shift: snap to 15° | Release to confirm."
        return "Click and drag to draw a line. Shift: constrain angle."

    @property
    def _item(self) -> LineItem | None:
        """The line being drawn: the shared drawing preview, typed."""
        item = self._preview_item
        return item if isinstance(item, LineItem) else None

    @property
    def drawing_measurement(self) -> tuple[str, ...]:
        """3.2's dimension tooltip: the length and the angle from the horizontal."""
        item = self._item
        if item is None:
            return ()
        return (length_angle_text(item.line.dx(), item.line.dy()),)

    def _drawing_bounds(self) -> QRectF | None:
        item = self._item
        if item is None:
            return None
        return item.mapRectToScene(QRectF(item.line.p1(), item.line.p2()).normalized())

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        self._start = self._snap_pos(
            self._scene.views()[0].mapToScene(event.pos()) if self._scene.views() else QPointF()
        )
        item = LineItem(line=QLineF(QPointF(0, 0), QPointF(0, 0)))
        item.apply_creation_defaults(self._creation_defaults)
        item.setPos(self._start)
        self._start_preview(item)
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        item = self._item
        if item is None or self._scene is None:
            return False
        current = self._snap_pos(
            self._scene.views()[0].mapToScene(event.pos()) if self._scene.views() else QPointF()
        )
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Shift snaps the angle to 15-degree steps (Basic Shape PRD 3.2)
            current = constrain_angle(self._start, current)
        local_end = current - self._start
        item.line = QLineF(QPointF(0, 0), local_end)
        self._show_drawing_feedback(event)
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        created_item = self._item
        if created_item is None or self._scene is None:
            return False
        self._end_preview()
        if created_item.line.length() > 2:
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                # 2.1, 2.5: the tool stays active and the new item is not selected (decision 2)
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)
        return True
