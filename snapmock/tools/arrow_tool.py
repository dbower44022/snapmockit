"""ArrowTool — click-and-drag to create arrows.

Basic Shape PRD 4.7: the shared set, then Head Style, Tail Style, Head Size with its custom
spin box, and the tool's own Line Style toggles (Straight, Curved, Elbow) with icons drawn
from the item itself. A curved or elbow arrow is drawn straight and bent afterwards in
point-editing mode (4.5, 4.6).
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QButtonGroup, QLabel, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
    HeadSize,
    HeadStyle,
    LineStyle,
)
from snapmock.core.path_utils import constrain_angle
from snapmock.items.arrow_item import ArrowItem
from snapmock.tools.base_tool import BaseTool

_LINE_STYLES: tuple[tuple[LineStyle, str, str], ...] = (
    (LineStyle.STRAIGHT, "Straight", "Straight line"),
    (LineStyle.CURVED, "Curved", "Curved line: bend it by its control point in point editing"),
    (LineStyle.ELBOW, "Elbow", "Elbow connector: move its bend point in point editing"),
)
_CONTROL_HEIGHT = 26


def line_style_icon(style: LineStyle, size: int = 20) -> QIcon:
    """A small arrow drawn in *style*, the toggle's icon (Basic Shape PRD 4.7)."""
    item = ArrowItem(line=QLineF(3.0, size - 4.0, size - 3.0, 4.0))
    item.stroke_width = 1.5
    item.stroke_color = QColor(90, 90, 90)
    item.head_size = HeadSize.SMALL
    item.head_size_custom = 5.0
    item.line_style = style
    if style is LineStyle.CURVED:
        item.control_point = QPointF(3.0, 4.0)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    item.paint(painter, None)
    painter.end()
    return QIcon(pixmap)


class ArrowTool(BaseTool):
    """Interactive tool for creating arrows by click-and-drag."""

    # Tool Options Bar shared controls (General UI PRD 5.3), then the tool's own Line
    # Style toggles (Basic Shape PRD 4.7)
    options_controls = (
        "stroke_color",
        "stroke_width",
        "stroke_style",
        "stroke_opacity",
        "shadow_enabled",
        "head_style",
        "tail_style",
        "head_size",
        "head_size_custom",
    )

    def __init__(self) -> None:
        super().__init__()
        self._start: QPointF = QPointF()
        self._line_style_buttons: dict[LineStyle, QToolButton] = {}
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
            "head_style": HeadStyle.OPEN,
            "tail_style": HeadStyle.NONE,
            "head_size": HeadSize.MEDIUM,
            "head_size_custom": 0.0,
            "line_style": LineStyle.STRAIGHT,
        }

    @property
    def tool_id(self) -> str:
        return "arrow"

    @property
    def display_name(self) -> str:
        return "Arrow"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def status_hint(self) -> str:
        return "Click and drag to draw arrow | Shift: constrain angle"

    # ------------------------------------------------------------ the options bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Line Style toggles with their icons (PRD 4.7)."""
        toolbar.addWidget(QLabel(" Line:"))
        group = QButtonGroup(toolbar)
        group.setExclusive(True)
        self._line_style_buttons = {}
        for style, name, tip in _LINE_STYLES:
            button = QToolButton()
            button.setCheckable(True)
            button.setIcon(line_style_icon(style))
            button.setToolTip(tip)
            button.setAccessibleName(f"{name} line style")
            button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
            button.toggled.connect(
                lambda checked, s=style: self._on_line_style_toggled(s, checked)
            )
            group.addButton(button)
            toolbar.addWidget(button)
            self._line_style_buttons[style] = button
        self._sync_line_style_buttons()

    @property
    def line_style_buttons(self) -> dict[LineStyle, QToolButton]:
        return dict(self._line_style_buttons)

    def _sync_line_style_buttons(self) -> None:
        current = self._creation_defaults.get("line_style", LineStyle.STRAIGHT)
        for style, button in self._line_style_buttons.items():
            button.blockSignals(True)
            button.setChecked(style is current)
            button.blockSignals(False)

    def _on_line_style_toggled(self, style: LineStyle, checked: bool) -> None:
        if not checked:
            return
        self._creation_defaults["line_style"] = style
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def on_option_changed(self, key: str, value: Any) -> None:
        if key == "line_style":
            self._sync_line_style_buttons()

    # ------------------------------------------------------------ drawing

    @property
    def _item(self) -> ArrowItem | None:
        """The arrow being drawn: the shared drawing preview, typed."""
        item = self._preview_item
        return item if isinstance(item, ArrowItem) else None

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        self._start = self._snap_pos(
            self._scene.views()[0].mapToScene(event.pos()) if self._scene.views() else QPointF()
        )
        item = ArrowItem(line=QLineF(QPointF(0, 0), QPointF(0, 0)))
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
            # Shift snaps the angle to 15-degree steps (Basic Shape PRD 3.2, 4.2)
            current = constrain_angle(self._start, current)
        local_end = current - self._start
        item.line = QLineF(QPointF(0, 0), local_end)
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        created_item = self._item
        if created_item is None or self._scene is None:
            return False
        self._end_preview()
        if created_item.line.length() > 2:
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                if self._selection_manager is not None:
                    self._selection_manager.select(created_item)
                self._switch_to_select()
        return True
