"""RectangleTool — click-and-drag to create rectangles.

Basic Shape PRD 5.4: the shared set, the Corner Radius slider and spin box, and the tool's
own Uniform / Individual toggle; in Individual mode four small spin boxes (top-left,
top-right, bottom-left, bottom-right) replace the single slider.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QMouseEvent
from PyQt6.QtWidgets import QLabel, QSpinBox, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    CORNER_KEYS,
    CORNER_RADIUS_MAX,
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
    CornerRadiusMode,
)
from snapmock.core.path_utils import constrained_rect
from snapmock.items.rectangle_item import RectangleItem
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.dimension_overlay import size_text

_CORNER_NAMES: dict[str, tuple[str, str]] = {
    "corner_radius_tl": ("TL", "Top-left corner radius"),
    "corner_radius_tr": ("TR", "Top-right corner radius"),
    "corner_radius_bl": ("BL", "Bottom-left corner radius"),
    "corner_radius_br": ("BR", "Bottom-right corner radius"),
}
_CONTROL_HEIGHT = 26


class RectangleTool(BaseTool):
    """Interactive tool for creating rectangles by click-and-drag."""

    # Tool Options Bar shared controls (General UI PRD 5.3)
    options_controls = (
        "stroke_color",
        "fill_color",
        "stroke_width",
        "stroke_style",
        "fill_opacity",
        "stroke_opacity",
        "shadow_enabled",
        "corner_radius",
    )

    def __init__(self) -> None:
        super().__init__()
        self._start: QPointF = QPointF()
        self._toolbar: QToolBar | None = None
        self._mode_button: QToolButton | None = None
        self._corner_spins: dict[str, QSpinBox] = {}
        self._corner_actions: list[QAction] = []
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "fill_color": QColor(DEFAULT_FILL_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
            "corner_radius": 0.0,
            "corner_radius_mode": CornerRadiusMode.UNIFORM,
            **dict.fromkeys(CORNER_KEYS, 0.0),
        }

    @property
    def tool_id(self) -> str:
        return "rectangle"

    @property
    def display_name(self) -> str:
        return "Rectangle"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def status_hint(self) -> str:
        """5.7's Idle row, with the centre-draw modifier's second route (decision 4)."""
        return "Click and drag to draw a rectangle. Shift: square. Alt or Ctrl: from center."

    # ------------------------------------------------------------ the options bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Uniform / Individual toggle and the four corner spin boxes (PRD 5.4)."""
        self._toolbar = toolbar
        button = QToolButton()
        button.setCheckable(True)
        button.setText("Individual")
        button.setToolTip("Individual corners: a radius for each corner")
        button.setAccessibleName("Individual corner radii")
        button.setMaximumHeight(_CONTROL_HEIGHT)
        button.toggled.connect(self._on_mode_toggled)
        toolbar.addWidget(button)
        self._mode_button = button
        self._corner_spins = {}
        self._corner_actions = []
        for key in CORNER_KEYS:
            short, name = _CORNER_NAMES[key]
            label_action = toolbar.addWidget(QLabel(f" {short}:"))
            spin = QSpinBox()
            spin.setRange(0, int(CORNER_RADIUS_MAX))
            spin.setSuffix(" px")
            spin.setMaximumWidth(64)
            spin.setMaximumHeight(_CONTROL_HEIGHT)
            spin.setToolTip(name)
            spin.setAccessibleName(name)
            spin.valueChanged.connect(lambda v, k=key: self._on_corner_changed(k, v))
            spin_action = toolbar.addWidget(spin)
            self._corner_spins[key] = spin
            self._corner_actions.extend(a for a in (label_action, spin_action) if a is not None)
        self._sync_corner_controls()

    @property
    def mode_button(self) -> QToolButton | None:
        return self._mode_button

    @property
    def corner_spins(self) -> dict[str, QSpinBox]:
        return dict(self._corner_spins)

    def _individual(self) -> bool:
        return self._creation_defaults.get("corner_radius_mode") is CornerRadiusMode.INDIVIDUAL

    def _sync_corner_controls(self) -> None:
        """Show the four spin boxes in Individual mode and the single slider otherwise."""
        individual = self._individual()
        if self._mode_button is not None:
            self._mode_button.blockSignals(True)
            self._mode_button.setChecked(individual)
            self._mode_button.blockSignals(False)
        for key, spin in self._corner_spins.items():
            spin.blockSignals(True)
            spin.setValue(int(round(float(self._creation_defaults.get(key, 0.0)))))
            spin.blockSignals(False)
        for action in self._corner_actions:
            action.setVisible(individual)
        show_uniform = getattr(self._toolbar, "set_control_visible", None)
        if callable(show_uniform):
            show_uniform("corner_radius", not individual)

    def _announce(self) -> None:
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def _on_mode_toggled(self, checked: bool) -> None:
        mode = CornerRadiusMode.INDIVIDUAL if checked else CornerRadiusMode.UNIFORM
        if mode is CornerRadiusMode.INDIVIDUAL and not any(
            float(self._creation_defaults.get(k, 0.0)) for k in CORNER_KEYS
        ):
            # The four start from the uniform radius, so the next rectangle looks the same
            for key in CORNER_KEYS:
                self._creation_defaults[key] = float(self._creation_defaults["corner_radius"])
        self._creation_defaults["corner_radius_mode"] = mode
        self._sync_corner_controls()
        self._announce()

    def _on_corner_changed(self, key: str, value: int) -> None:
        self._creation_defaults[key] = float(value)
        self._announce()

    def on_option_changed(self, key: str, value: Any) -> None:
        if key == "corner_radius_mode" or key in CORNER_KEYS:
            self._sync_corner_controls()

    # ------------------------------------------------------------ drawing

    @property
    def _item(self) -> RectangleItem | None:
        """The rectangle being drawn: the shared drawing preview, typed."""
        item = self._preview_item
        return item if isinstance(item, RectangleItem) else None

    @property
    def drawing_measurement(self) -> tuple[str, ...]:
        """5.2's dimension tooltip: the width and the height, as the modifiers left them."""
        item = self._item
        if item is None:
            return ()
        return (size_text(item.rect.width(), item.rect.height()),)

    def _centre_marker_origin(self) -> QPointF | None:
        if self._item is None or not self.draws_from_centre(self._drawing_modifiers):
            return None
        return QPointF(self._start)

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        self._start = self._snap_pos(
            self._scene.views()[0].mapToScene(event.pos()) if self._scene.views() else QPointF()
        )
        item = RectangleItem(rect=QRectF(0, 0, 0, 0))
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
        # 2.3: Shift squares the rectangle, the centre-draw modifier grows it from the
        # press point; either takes effect from the move it is first seen on
        modifiers = event.modifiers()
        rect = constrained_rect(
            self._start,
            current,
            square=self.constrains(modifiers),
            from_centre=self.draws_from_centre(modifiers),
        )
        item.setPos(rect.topLeft())
        item.rect = QRectF(0, 0, rect.width(), rect.height())
        self._show_drawing_feedback(event)
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        created_item = self._item
        if created_item is None or self._scene is None:
            return False
        # Take the preview out of the scene; it never joined a layer's item list
        self._end_preview()
        # Only create if it has meaningful size
        if created_item.rect.width() > 2 and created_item.rect.height() > 2:
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                if self._selection_manager is not None:
                    self._selection_manager.select(created_item)
                self._switch_to_select()
        return True
