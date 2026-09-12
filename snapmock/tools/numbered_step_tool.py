"""NumberedStepTool — click to place a numbered step, drag to size it (PRD Section 2).

Numbered Steps, Stamps & Emoji PRD Sections 2.2, 2.3, 2.7, and 2.11: a click places the
next number centred on the click point at the default size; a drag of ten pixels or more
sets the diameter to twice the distance from the centre; the counter is per project, is
not reset by a tool switch, starts at the Starting Number, and continues from the highest
step in a loaded project; the Tool Options Bar composes the tool's controls from
:attr:`options_controls` and the tool adds the Renumber All button.
"""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QAbstractAnimation, QPointF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QCursor, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QPushButton, QToolBar

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    BADGE_SIZE_MAX,
    BADGE_SIZE_MIN,
    DEFAULT_BADGE_BORDER_COLOR,
    DEFAULT_BADGE_BORDER_WIDTH,
    DEFAULT_BADGE_COLOR,
    DEFAULT_BADGE_SIZE,
    DEFAULT_BADGE_TEXT_COLOR,
    BadgeShape,
    BorderStyle,
    DisplayMode,
    FontWeight,
)
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.cursors import numbered_step_cursor

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager

MIN_DRAG_DISTANCE = 10.0
"""A drag shorter than this is a click and places the default size (PRD 2.2)."""
PLACEMENT_HINT_MS = 2000
"""How long "Placed Step N" stays in the status bar (kickoff silence 4)."""
PLACEMENT_ANIMATION_MS = 150
PLACEMENT_START_SCALE = 1.2

ANIMATIONS_ENABLED = True
"""Tests set this False so a placed item lands at scale 1 at once (kickoff silence 4)."""


def animate_placement(
    item: SnapGraphicsItem, start_scale: float, duration_ms: int, parent: Any = None
) -> QVariantAnimation | None:
    """Scale *item* from *start_scale* to 1 over *duration_ms*; None when animations are off.

    The animation is not a command and is not saved; the item's scale is 1 when it ends.
    """
    if not ANIMATIONS_ENABLED:
        item.setScale(1.0)
        return None
    item.setScale(float(start_scale))
    animation = QVariantAnimation(parent)
    animation.setStartValue(float(start_scale))
    animation.setEndValue(1.0)
    animation.setDuration(duration_ms)
    animation.valueChanged.connect(lambda value: item.setScale(float(value)))
    animation.finished.connect(lambda: item.setScale(1.0))
    animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation


class NumberedStepTool(BaseTool):
    """Click to place incrementing numbered step markers; drag to size one."""

    # The Tool Options Bar of PRD 2.7, in its order; "tool" is the Renumber All button.
    options_controls = (
        "badge_color",
        "text_color",
        "badge_shape",
        "badge_size",
        "start_number",
        "display_mode",
        "font_weight",
        "border_width",
        "border_color",
        "border_style",
        "shadow_enabled",
        "tool",
    )

    def __init__(self) -> None:
        super().__init__()
        self._creation_defaults = {
            "badge_color": QColor(DEFAULT_BADGE_COLOR),
            "text_color": QColor(DEFAULT_BADGE_TEXT_COLOR),
            "badge_shape": BadgeShape.CIRCLE,
            "badge_size": DEFAULT_BADGE_SIZE,
            "start_number": 1,
            "display_mode": DisplayMode.NUMBER,
            "font_weight": FontWeight.BOLD,
            "border_width": DEFAULT_BADGE_BORDER_WIDTH,
            "border_color": QColor(DEFAULT_BADGE_BORDER_COLOR),
            "border_style": BorderStyle.SOLID,
            "shadow_enabled": True,
        }
        # The counter is per project (PRD 2.3): one entry per scene, kept across tool
        # switches, dropped with the scene.
        self._counters: weakref.WeakKeyDictionary[SnapScene, int] = weakref.WeakKeyDictionary()
        self._drag_start: QPointF | None = None
        self._drag_preview: QGraphicsEllipseItem | None = None
        self._drag_size: float | None = None
        self._placed_hint: str | None = None
        self._hint_timer: QTimer | None = None

    # ------------------------------------------------------------ identity

    @property
    def tool_id(self) -> str:
        return "numbered_step"

    @property
    def display_name(self) -> str:
        return "Numbered Step"

    @property
    def cursor(self) -> Qt.CursorShape | QCursor:
        return numbered_step_cursor()

    @property
    def status_hint(self) -> str:
        """PRD 2.11: the idle hint names the next number; "Placed Step N" for two seconds."""
        if self._placed_hint is not None:
            return self._placed_hint
        n = self.next_number
        return f"Click to place step {n}. Drag to set size. Next: {n}."

    @property
    def is_active_operation(self) -> bool:
        return self._drag_start is not None

    # ------------------------------------------------------------ the counter

    @property
    def next_number(self) -> int:
        """The number the next click places (PRD 2.3)."""
        scene = self._scene
        if scene is None:
            return int(self._creation_defaults.get("start_number", 1))
        return self._counters.get(scene, self._initial_number(scene))

    def _initial_number(self, scene: SnapScene) -> int:
        """A project's first counter value: the highest step plus one (PRD 7.1), else the
        Starting Number."""
        numbers = [
            item.number_value
            for item in scene.all_annotation_items()
            if isinstance(item, NumberedStepItem) and item.display_mode is not DisplayMode.TEXT
        ]
        if numbers:
            return max(numbers) + 1
        return int(self._creation_defaults.get("start_number", 1))

    def set_next_number(self, value: int) -> None:
        """Set the counter for the active project (the Starting Number control, Set as
        Starting Number, a renumber)."""
        if self._scene is not None:
            self._counters[self._scene] = int(value)
            self._show_idle_hint()

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        if scene not in self._counters:
            self._counters[scene] = self._initial_number(scene)

    def deactivate(self) -> None:
        self._cleanup_drag()
        self._clear_placed_hint()
        super().deactivate()

    def cancel(self) -> None:
        self._cleanup_drag()

    def on_option_changed(self, key: str, value: object) -> None:
        """Starting Number sets the next number to be placed (PRD 2.7)."""
        if key == "start_number":
            self.set_next_number(int(value))  # type: ignore[call-overload]

    # ------------------------------------------------------------ the bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Renumber All button (PRD 2.7); every other control is a shared one."""
        button = QPushButton("Renumber All")
        button.setToolTip("Renumber every step top to bottom, then left to right")
        button.setAccessibleName("Renumber All")
        button.setMaximumHeight(26)
        button.clicked.connect(self._on_renumber_clicked)
        toolbar.addWidget(button)

    def _on_renumber_clicked(self) -> None:
        window = self._window()
        renumber = getattr(window, "renumber_all_steps", None)
        if callable(renumber):
            renumber()

    # ------------------------------------------------------------ placing

    def _layer_allows_placing(self) -> bool:
        """PRD 2.11 and 8.4: no step on a locked or hidden layer; the Section 1.3 message.

        The rule and its wording are ``BaseTool.layer_allows_drawing``'s, shared with
        every drawing tool since the shape tools' shared drawing work.
        """
        return self.layer_allows_drawing()

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        view = self._view
        if view is None:
            return False
        scene_pos = view.mapToScene(event.pos())
        existing = self._step_at(scene_pos)
        if existing is not None:
            # A click on an existing step selects it; a double-click then edits it (2.8)
            if self._selection_manager is not None:
                self._selection_manager.select(existing)
            return True
        if not self._layer_allows_placing():
            return True
        self._drag_start = self._snap_pos(scene_pos)
        self._drag_size = None
        return True

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        """A double-click on a step enters its inline edit (PRD 2.8; kickoff silence 9)."""
        view = self._view
        if view is None or self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        step = self._step_at(view.mapToScene(event.pos()))
        if step is None:
            return False
        self._cleanup_drag()
        open_editor = getattr(self._window(), "open_marker_editor", None)
        if callable(open_editor):
            open_editor(step)
        return True

    def _step_at(self, scene_pos: QPointF) -> NumberedStepItem | None:
        """The top-level numbered step under *scene_pos* on an unlocked, visible layer.

        A group's member is not found: it is edited after Ungroup (kickoff silence 14).
        """
        if self._scene is None:
            return None
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, NumberedStepItem) and gitem.parentItem() is None:
                layer = self._scene.layer_manager.layer_by_id(gitem.layer_id)
                if layer is not None and (layer.locked or not layer.visible):
                    continue
                return gitem
        return None

    def mouse_move(self, event: QMouseEvent) -> bool:
        view = self._view
        if view is None or self._scene is None or self._drag_start is None:
            return False
        current = view.mapToScene(event.pos())
        distance = QPointF(current - self._drag_start).manhattanLength()
        dx = current.x() - self._drag_start.x()
        dy = current.y() - self._drag_start.y()
        radius = (dx * dx + dy * dy) ** 0.5
        if radius < MIN_DRAG_DISTANCE and distance < MIN_DRAG_DISTANCE:
            self._drag_size = None
            self._cleanup_drag_preview()
            return True
        # Diameter is twice the distance from the centre (PRD 2.2); Shift changes nothing
        # because the badge has one size in every shape (kickoff silence, step 3).
        self._drag_size = max(BADGE_SIZE_MIN, min(BADGE_SIZE_MAX, 2.0 * radius))
        if self._drag_preview is None:
            preview = QGraphicsEllipseItem()
            pen = QPen(QColor("#0078d7"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            preview.setZValue(1e9)
            self._scene.addItem(preview)
            self._drag_preview = preview
        half = self._drag_size / 2
        self._drag_preview.setRect(
            self._drag_start.x() - half, self._drag_start.y() - half, 2 * half, 2 * half
        )
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._scene is None or self._drag_start is None:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        center = self._drag_start
        size = self._drag_size
        self._cleanup_drag()
        self.place(center, size)
        return True

    def place(self, center: QPointF, size: float | None = None) -> NumberedStepItem | None:
        """Place the next step centred on *center* (its pin point for the pin shape) at
        *size*, or the default badge size; push the AddItemCommand; advance the counter."""
        scene = self._scene
        if scene is None:
            return None
        layer = scene.layer_manager.active_layer
        if layer is None:
            return None
        number = self.next_number
        item = NumberedStepItem(number_value=number)
        self._apply_creation_defaults(item)
        if size is not None:
            item.badge_size = size
        item.setPos(center)
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        if item.display_mode is not DisplayMode.TEXT:
            self._counters[scene] = number + 1
        animate_placement(item, PLACEMENT_START_SCALE, PLACEMENT_ANIMATION_MS, scene)
        self._show_placed_hint(number)
        return item

    def _apply_creation_defaults(self, item: NumberedStepItem) -> None:
        d = self._creation_defaults
        item.badge_color = QColor(d.get("badge_color", QColor(DEFAULT_BADGE_COLOR)))
        item.text_color = QColor(d.get("text_color", QColor(DEFAULT_BADGE_TEXT_COLOR)))
        shape = d.get("badge_shape", BadgeShape.CIRCLE)
        item.badge_shape = shape if isinstance(shape, BadgeShape) else BadgeShape.CIRCLE
        item.badge_size = float(d.get("badge_size", DEFAULT_BADGE_SIZE))
        mode = d.get("display_mode", DisplayMode.NUMBER)
        item.display_mode = mode if isinstance(mode, DisplayMode) else DisplayMode.NUMBER
        weight = d.get("font_weight", FontWeight.BOLD)
        item.font_weight = weight if isinstance(weight, FontWeight) else FontWeight.BOLD
        item.border_width = float(d.get("border_width", DEFAULT_BADGE_BORDER_WIDTH))
        item.border_color = QColor(d.get("border_color", QColor(DEFAULT_BADGE_BORDER_COLOR)))
        style = d.get("border_style", BorderStyle.SOLID)
        item.border_style = style if isinstance(style, BorderStyle) else BorderStyle.SOLID
        item.shadow_enabled = bool(d.get("shadow_enabled", True))

    # ------------------------------------------------------------ hints

    def _show_placed_hint(self, number: int) -> None:
        self._placed_hint = (
            f"Placed Step {number}. Click to place Step {self.next_number}."
            if self._scene is not None
            else None
        )
        self._push_hint()
        if self._hint_timer is None:
            self._hint_timer = QTimer()
            self._hint_timer.setSingleShot(True)
            self._hint_timer.timeout.connect(self._show_idle_hint)
        self._hint_timer.start(PLACEMENT_HINT_MS)

    def _show_idle_hint(self) -> None:
        self._clear_placed_hint()
        self._push_hint()

    def _clear_placed_hint(self) -> None:
        self._placed_hint = None
        if self._hint_timer is not None and self._hint_timer.isActive():
            self._hint_timer.stop()

    def _push_hint(self) -> None:
        window = self._window()
        show = getattr(window, "show_status_hint", None)
        if callable(show) and self._scene is not None:
            show(self.status_hint)

    # ------------------------------------------------------------ drag cleanup

    def _cleanup_drag_preview(self) -> None:
        if self._drag_preview is not None:
            if self._scene is not None and self._drag_preview.scene() is self._scene:
                self._scene.removeItem(self._drag_preview)
            self._drag_preview = None

    def _cleanup_drag(self) -> None:
        self._cleanup_drag_preview()
        self._drag_start = None
        self._drag_size = None
