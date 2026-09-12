"""ArcTool — the three-step arc of Basic Shape PRD Section 7.

Step 1 drags the chord (Shift constrains its angle to 15-degree steps); step 2 moves the
mouse with no button held, the arc bulging toward the cursor on either side of the chord;
a click, a double-click, or Enter confirms, and Escape cancels at any step (7.2). The Tool
Options Bar of 7.4: the shared set of 2.6, the Head Style, Tail Style, and Head Size
controls of the Arrow, and the tool's own Arc Type toggles.
"""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QButtonGroup, QLabel, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    ArcType,
    BorderStyle,
    HeadSize,
    HeadStyle,
)
from snapmock.core.path_utils import constrain_angle
from snapmock.items.arc_item import ArcItem
from snapmock.tools.base_tool import BaseTool

_ARC_TYPES: tuple[tuple[ArcType, str, str], ...] = (
    (ArcType.OPEN, "Open", "Open: the arc alone"),
    (ArcType.CHORD, "Chord", "Chord: the arc closed by a straight line"),
    (ArcType.PIE, "Pie", "Pie: the arc closed through its centre"),
)
_CONTROL_HEIGHT = 26
MIN_CHORD = 2.0
"""A chord shorter than this on release is an accidental click."""


def arc_type_icon(arc_type: ArcType, size: int = 20) -> QIcon:
    """A small arc of *arc_type*, the toggle's icon (7.4)."""
    item = ArcItem(
        start=QPointF(3.0, size - 5.0),
        end=QPointF(size - 3.0, size - 5.0),
        control=QPointF(size / 2.0, -size * 0.45),
    )
    item.stroke_width = 1.5
    item.stroke_color = QColor(90, 90, 90)
    item.fill_color = QColor(90, 90, 90, 90)
    item.arc_type = arc_type
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    item.paint(painter, None)
    painter.end()
    return QIcon(pixmap)


class _Step(Enum):
    IDLE = auto()
    CHORD = auto()
    CURVE = auto()


class ArcTool(BaseTool):
    """Interactive tool for creating arcs in three steps."""

    options_controls = (
        "stroke_color",
        "fill_color",
        "stroke_width",
        "stroke_style",
        "fill_opacity",
        "stroke_opacity",
        "shadow_enabled",
        "head_style",
        "tail_style",
        "head_size",
    )

    def __init__(self) -> None:
        super().__init__()
        self._step = _Step.IDLE
        self._start = QPointF()
        self._item: ArcItem | None = None
        self._arc_type_buttons: dict[ArcType, QToolButton] = {}
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "fill_color": QColor(DEFAULT_FILL_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
            "head_style": HeadStyle.NONE,
            "tail_style": HeadStyle.NONE,
            "head_size": HeadSize.MEDIUM,
            "arc_type": ArcType.OPEN,
        }

    @property
    def tool_id(self) -> str:
        return "arc"

    @property
    def display_name(self) -> str:
        return "Arc"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def is_active_operation(self) -> bool:
        return self._step is not _Step.IDLE

    @property
    def preview(self) -> ArcItem | None:
        return self._item

    @property
    def status_hint(self) -> str:
        """The hints of 7.7, with the dimension tooltip's values (7.2)."""
        item = self._item
        if self._step is _Step.CHORD and item is not None:
            chord = item.end_point - item.start_point
            length = math.hypot(chord.x(), chord.y())
            angle = -math.degrees(math.atan2(chord.y(), chord.x()))
            return (
                f"L: {length:.0f}px ∠ {angle:.1f}° | Shift: constrain angle | "
                "Release to set chord."
            )
        if self._step is _Step.CURVE and item is not None:
            mid = (item.start_point + item.end_point) / 2.0
            peak = item.peak()
            bulge = math.hypot(peak.x() - mid.x(), peak.y() - mid.y())
            return (
                f"Arc: {item.curve_path().length():.0f}px Bulge: {bulge:.0f}px | "
                "Move mouse to adjust curvature. Click to confirm. Escape to cancel."
            )
        return "Click and drag to define the arc chord. Then move to set curvature."

    def _show_hint(self) -> None:
        view = self._view
        window = view.window() if view is not None else None
        show = getattr(window, "show_status_hint", None)
        if callable(show):
            show(self.status_hint)

    # ------------------------------------------------------------ the options bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Arc Type toggles with their icons (7.4)."""
        toolbar.addWidget(QLabel(" Type:"))
        group = QButtonGroup(toolbar)
        group.setExclusive(True)
        self._arc_type_buttons = {}
        for arc_type, name, tip in _ARC_TYPES:
            button = QToolButton()
            button.setCheckable(True)
            button.setIcon(arc_type_icon(arc_type))
            button.setToolTip(tip)
            button.setAccessibleName(f"{name} arc type")
            button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
            button.toggled.connect(lambda checked, t=arc_type: self._on_type_toggled(t, checked))
            group.addButton(button)
            toolbar.addWidget(button)
            self._arc_type_buttons[arc_type] = button
        self._sync_buttons()

    @property
    def arc_type_buttons(self) -> dict[ArcType, QToolButton]:
        return dict(self._arc_type_buttons)

    def _sync_buttons(self) -> None:
        current = self._creation_defaults.get("arc_type", ArcType.OPEN)
        for arc_type, button in self._arc_type_buttons.items():
            button.blockSignals(True)
            button.setChecked(arc_type is current)
            button.blockSignals(False)

    def _on_type_toggled(self, arc_type: ArcType, checked: bool) -> None:
        if not checked:
            return
        self._creation_defaults["arc_type"] = arc_type
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def on_option_changed(self, key: str, value: Any) -> None:
        if key == "arc_type":
            self._sync_buttons()

    # ------------------------------------------------------------ the three steps

    def _scene_pos(self, event: QMouseEvent) -> QPointF:
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0].mapToScene(event.pos())
        return QPointF()

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._step is _Step.CURVE:
            self._confirm()
            return True
        if self._step is _Step.CHORD:
            return True
        if not self.layer_allows_drawing():
            return True
        self._start = self._snap_pos(self._scene_pos(event))
        self._item = ArcItem(start=QPointF(0, 0), end=QPointF(0, 0), control=QPointF(0, 0))
        self._item.apply_creation_defaults(self._creation_defaults)
        self._item.setPos(self._start)
        self._scene.addItem(self._item)
        self._step = _Step.CHORD
        self._show_hint()
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        item = self._item
        if item is None or self._step is _Step.IDLE:
            return False
        pos = self._scene_pos(event)
        if self._step is _Step.CHORD:
            current = self._snap_pos(pos)
            if self.constrains(event.modifiers()):
                current = constrain_angle(self._start, current)
            if self.draws_from_centre(event.modifiers()):
                # 2.3 lists the Arc under the centre-draw modifier and Section 7 does not
                # say what it does: the press point becomes the chord's midpoint, so the
                # chord grows both ways at once (notes Section 6)
                half = current - self._start
                item.setPos(self._start - half)
                item.end_point = half * 2.0
            else:
                item.setPos(self._start)
                item.end_point = current - self._start
            item.control_point = item.end_point / 2.0
        else:
            # The item's own position, not the press point: the centre-draw modifier of
            # 2.3 moves the chord's start away from where the press landed
            item.control_point = self.control_for(pos - item.pos())
        self._show_hint()
        return True

    def control_for(self, cursor: QPointF) -> QPointF:
        """The control point that puts the arc's peak level with *cursor* (item
        coordinates) on the chord's perpendicular through its midpoint, either side (7.2)."""
        item = self._item
        if item is None:
            return QPointF(cursor)
        start, end = item.start_point, item.end_point
        chord = end - start
        length = math.hypot(chord.x(), chord.y())
        mid = (start + end) / 2.0
        if length <= 1e-9:
            return mid
        normal = QPointF(-chord.y() / length, chord.x() / length)
        offset = cursor - mid
        distance = offset.x() * normal.x() + offset.y() * normal.y()
        # The quadratic's peak is halfway from the chord's midpoint to the control point
        return mid + normal * (2.0 * distance)

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._step is not _Step.CHORD or self._item is None:
            return self._step is not _Step.IDLE
        chord = self._item.end_point - self._item.start_point
        if math.hypot(chord.x(), chord.y()) < MIN_CHORD:
            self.cancel()
            return True
        self._step = _Step.CURVE
        self._show_hint()
        return True

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        if self._step is _Step.CURVE:
            self._confirm()
            return True
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if self._step is _Step.CURVE and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm()
            return True
        if event.key() == Qt.Key.Key_Escape:
            return self.handle_escape()
        return False

    def handle_escape(self) -> bool:
        """Escape cancels the whole arc at any step (7.2)."""
        if self._step is _Step.IDLE:
            return False
        self.cancel()
        return True

    def cancel(self) -> None:
        if self._item is not None and self._scene is not None and self._item.scene() is not None:
            self._scene.removeItem(self._item)
        self._item = None
        self._step = _Step.IDLE
        self._show_hint()

    def deactivate(self) -> None:
        self.cancel()
        super().deactivate()

    def _confirm(self) -> None:
        item, scene = self._item, self._scene
        self._item = None
        self._step = _Step.IDLE
        if item is None or scene is None:
            return
        scene.removeItem(item)
        layer = scene.layer_manager.active_layer
        if layer is None:
            return
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        if self._selection_manager is not None:
            self._selection_manager.select(item)
        self._switch_to_select()
