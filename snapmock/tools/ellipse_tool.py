"""EllipseTool — click-and-drag to create ellipses."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
)
from snapmock.core.path_utils import constrained_rect
from snapmock.items.ellipse_item import EllipseItem
from snapmock.tools.base_tool import BaseTool


class EllipseTool(BaseTool):
    """Interactive tool for creating ellipses by click-and-drag."""

    # Tool Options Bar shared controls (General UI PRD 5.3)
    options_controls = (
        "stroke_color",
        "fill_color",
        "stroke_width",
        "stroke_style",
        "fill_opacity",
        "stroke_opacity",
        "shadow_enabled",
    )

    def __init__(self) -> None:
        super().__init__()
        self._start: QPointF = QPointF()
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "fill_color": QColor(DEFAULT_FILL_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
        }

    @property
    def tool_id(self) -> str:
        return "ellipse"

    @property
    def display_name(self) -> str:
        return "Ellipse"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def status_hint(self) -> str:
        """6.7's Idle row, with the centre-draw modifier's second route (decision 4)."""
        return "Click and drag to draw an ellipse. Shift: circle. Alt or Ctrl: from center."

    @property
    def _item(self) -> EllipseItem | None:
        """The ellipse being drawn: the shared drawing preview, typed."""
        item = self._preview_item
        return item if isinstance(item, EllipseItem) else None

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        self._start = self._snap_pos(
            self._scene.views()[0].mapToScene(event.pos()) if self._scene.views() else QPointF()
        )
        item = EllipseItem(rect=QRectF(0, 0, 0, 0))
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
        # 2.3 and 6.2: Shift makes the bounding rectangle a square, so the ellipse is a
        # circle; the centre-draw modifier puts the centre at the press point
        modifiers = event.modifiers()
        rect = constrained_rect(
            self._start,
            current,
            square=self.constrains(modifiers),
            from_centre=self.draws_from_centre(modifiers),
        )
        item.setPos(rect.topLeft())
        item.rect = QRectF(0, 0, rect.width(), rect.height())
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        created_item = self._item
        if created_item is None or self._scene is None:
            return False
        self._end_preview()
        if created_item.rect.width() > 2 and created_item.rect.height() > 2:
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                if self._selection_manager is not None:
                    self._selection_manager.select(created_item)
                self._switch_to_select()
        return True
