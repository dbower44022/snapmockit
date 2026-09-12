"""PolygonTool — freeform and regular polygons (Basic Shape PRD Section 8).

Freeform (8.2): each click places a vertex, Shift constraining the new edge to 15-degree
steps; a double-click, a click within 10 px of the first vertex, or Enter closes the
polygon; a right-click removes the last vertex; Escape cancels; fewer than three vertices
cancel on close (two for an open polyline). A dashed, faint line shows how the polygon
would close. Regular: press for the centre and drag for the radius and the first vertex's
angle, Shift snapping the angle to 15-degree steps; release confirms. The Tool Options
Bar of 8.4: the shared set of 2.6, then the tool's Mode toggles, Sides, Star, Star Indent,
and the Closed / Open toggle, each shown for the mode it serves.
"""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGraphicsPathItem,
    QLabel,
    QSlider,
    QSpinBox,
    QToolBar,
    QToolButton,
)

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
    PolygonMode,
)
from snapmock.core.path_utils import constrain_angle
from snapmock.items.polygon_item import SIDES_MAX, SIDES_MIN, PolygonItem
from snapmock.tools.base_tool import BaseTool

CLOSE_DISTANCE = 10.0
"""A click this close to the first vertex closes a freeform polygon (8.2)."""

MIN_RADIUS = 2.0
_CONTROL_HEIGHT = 26


class _Step(Enum):
    IDLE = auto()
    PLACING = auto()
    DRAGGING = auto()


class PolygonTool(BaseTool):
    """Interactive tool for polygons, stars, and open polylines."""

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
        self._step = _Step.IDLE
        self._points: list[QPointF] = []
        self._cursor = QPointF()
        self._center = QPointF()
        self._item: PolygonItem | None = None
        self._closing: QGraphicsPathItem | None = None
        self._mode_buttons: dict[PolygonMode, QToolButton] = {}
        self._sides_spin: QSpinBox | None = None
        self._star_check: QCheckBox | None = None
        self._indent_slider: QSlider | None = None
        self._closed_button: QToolButton | None = None
        self._regular_actions: list[QAction] = []
        self._indent_actions: list[QAction] = []
        self._freeform_actions: list[QAction] = []
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "fill_color": QColor(DEFAULT_FILL_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
            "polygon_mode": PolygonMode.FREEFORM,
            "sides": 5,
            "star_enabled": False,
            "star_indent": 0.5,
            "closed": True,
        }

    @property
    def tool_id(self) -> str:
        return "polygon"

    @property
    def display_name(self) -> str:
        return "Polygon"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    @property
    def is_active_operation(self) -> bool:
        return self._step is not _Step.IDLE

    @property
    def preview(self) -> PolygonItem | None:
        return self._item

    def _regular(self) -> bool:
        return self._creation_defaults.get("polygon_mode") is PolygonMode.REGULAR

    @property
    def drawing_measurement(self) -> tuple[str, ...]:
        """8.7's Drawing values, which the tooltip shows (2.4): the vertices placed so far,
        or a regular polygon's sides and radius."""
        if self._step is _Step.PLACING:
            return (f"Vertices: {len(self._points)}",)
        if self._step is _Step.DRAGGING and self._item is not None:
            return (f"Sides: {self._item.sides}", f"R: {self._item.radius or 0.0:.0f}px")
        return ()

    @property
    def status_hint(self) -> str:
        """The hints of 8.7, built from the tooltip's values."""
        measurement = " | ".join(self.drawing_measurement)
        if self._step is _Step.PLACING:
            return (
                f"{measurement} | Click: add vertex | Right-click: undo | "
                "Enter: close | Escape: cancel"
            )
        if self._step is _Step.DRAGGING and measurement:
            return f"{measurement} | Shift: constrain rotation | Release to confirm."
        if self._regular():
            return "Click and drag to draw a regular polygon. Shift: constrain rotation."
        return "Click to place vertices. Double-click or click first vertex to close."

    def _show_hint(self) -> None:
        view = self._view
        window = view.window() if view is not None else None
        show = getattr(window, "show_status_hint", None)
        if callable(show):
            show(self.status_hint)

    # ------------------------------------------------------------ the options bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """Mode, Sides, Star, Star Indent, and Closed / Open (8.4)."""
        toolbar.addWidget(QLabel(" Mode:"))
        group = QButtonGroup(toolbar)
        group.setExclusive(True)
        self._mode_buttons = {}
        for mode, name in ((PolygonMode.FREEFORM, "Freeform"), (PolygonMode.REGULAR, "Regular")):
            button = QToolButton()
            button.setCheckable(True)
            button.setText(name)
            button.setToolTip(f"{name} polygon")
            button.setAccessibleName(f"{name} polygon mode")
            button.setMaximumHeight(_CONTROL_HEIGHT)
            button.toggled.connect(lambda checked, m=mode: self._on_mode_toggled(m, checked))
            group.addButton(button)
            toolbar.addWidget(button)
            self._mode_buttons[mode] = button

        self._regular_actions = []
        label = toolbar.addWidget(QLabel(" Sides:"))
        sides = QSpinBox()
        sides.setRange(SIDES_MIN, SIDES_MAX)
        sides.setAccessibleName("Sides")
        sides.setMaximumHeight(_CONTROL_HEIGHT)
        sides.valueChanged.connect(lambda v: self._write("sides", int(v)))
        spin_action = toolbar.addWidget(sides)
        self._sides_spin = sides
        star = QCheckBox("Star")
        star.setAccessibleName("Star")
        star.setMaximumHeight(_CONTROL_HEIGHT)
        star.toggled.connect(lambda checked: self._write("star_enabled", bool(checked)))
        star_action = toolbar.addWidget(star)
        self._star_check = star
        self._regular_actions = [a for a in (label, spin_action, star_action) if a is not None]

        indent_label = toolbar.addWidget(QLabel(" Indent:"))
        indent = QSlider(Qt.Orientation.Horizontal)
        indent.setRange(10, 95)
        indent.setFixedWidth(80)
        indent.setAccessibleName("Star indent")
        indent.valueChanged.connect(lambda v: self._write("star_indent", v / 100.0))
        indent_action = toolbar.addWidget(indent)
        self._indent_slider = indent
        self._indent_actions = [a for a in (indent_label, indent_action) if a is not None]

        closed = QToolButton()
        closed.setCheckable(True)
        closed.setText("Closed")
        closed.setToolTip("Closed polygon; unchecked draws an open polyline")
        closed.setAccessibleName("Closed polygon")
        closed.setMaximumHeight(_CONTROL_HEIGHT)
        closed.toggled.connect(self._on_closed_toggled)
        closed_action = toolbar.addWidget(closed)
        self._closed_button = closed
        self._freeform_actions = [closed_action] if closed_action is not None else []
        self._sync_controls()

    @property
    def mode_buttons(self) -> dict[PolygonMode, QToolButton]:
        return dict(self._mode_buttons)

    @property
    def sides_spin(self) -> QSpinBox | None:
        return self._sides_spin

    @property
    def star_check(self) -> QCheckBox | None:
        return self._star_check

    @property
    def indent_slider(self) -> QSlider | None:
        return self._indent_slider

    @property
    def closed_button(self) -> QToolButton | None:
        return self._closed_button

    def control_actions(self) -> dict[str, list[QAction]]:
        """The bar's actions per group, for the visibility rules of 8.4."""
        return {
            "regular": list(self._regular_actions),
            "indent": list(self._indent_actions),
            "freeform": list(self._freeform_actions),
        }

    def _sync_controls(self) -> None:
        d = self._creation_defaults
        regular = self._regular()
        widgets: list[Any] = [
            *self._mode_buttons.values(),
            self._sides_spin,
            self._star_check,
            self._indent_slider,
            self._closed_button,
        ]
        for widget in widgets:
            if widget is not None:
                widget.blockSignals(True)
        for mode, button in self._mode_buttons.items():
            button.setChecked(mode is d.get("polygon_mode"))
        if self._sides_spin is not None:
            self._sides_spin.setValue(int(d.get("sides", 5)))
        if self._star_check is not None:
            self._star_check.setChecked(bool(d.get("star_enabled")))
        if self._indent_slider is not None:
            self._indent_slider.setValue(int(round(float(d.get("star_indent", 0.5)) * 100)))
        if self._closed_button is not None:
            self._closed_button.setChecked(bool(d.get("closed", True)))
        for widget in widgets:
            if widget is not None:
                widget.blockSignals(False)
        for action in self._regular_actions:
            action.setVisible(regular)
        for action in self._indent_actions:
            action.setVisible(regular and bool(d.get("star_enabled")))
        for action in self._freeform_actions:
            action.setVisible(not regular)

    def _write(self, key: str, value: Any) -> None:
        self._creation_defaults[key] = value
        self._sync_controls()
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def _on_mode_toggled(self, mode: PolygonMode, checked: bool) -> None:
        if checked:
            self.cancel()
            self._write("polygon_mode", mode)

    def _on_closed_toggled(self, checked: bool) -> None:
        self._write("closed", bool(checked))

    def on_option_changed(self, key: str, value: Any) -> None:
        if key in ("polygon_mode", "sides", "star_enabled", "star_indent", "closed"):
            self._sync_controls()

    # ------------------------------------------------------------ drawing

    def _scene_pos(self, event: QMouseEvent) -> QPointF:
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0].mapToScene(event.pos())
        return QPointF()

    def _placed(self, event: QMouseEvent) -> QPointF:
        """The cursor as the next vertex: snapped, and on a 15-degree ray with Shift."""
        pos = self._snap_pos(self._scene_pos(event))
        if self._points and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            pos = constrain_angle(self._points[-1], pos)
        return pos

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None:
            return False
        if event.button() == Qt.MouseButton.RightButton:
            if self._step is not _Step.PLACING:
                return False
            self._points.pop()  # right-click removes the last vertex (8.2)
            if not self._points:
                self.cancel()
            else:
                self._update_preview()
                self._show_drawing_feedback(event)
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # 2.1: the first press of a polygon is refused on a locked or hidden layer; the
        # presses that follow it place vertices in a shape already begun
        if self._step is _Step.IDLE and not self.layer_allows_drawing():
            return True
        if self._regular():
            self._begin_regular(self._snap_pos(self._scene_pos(event)))
            self._show_drawing_feedback(event)
            return True
        pos = self._placed(event)
        if (
            self._step is _Step.PLACING
            and len(self._points) >= 3
            and math.hypot(pos.x() - self._points[0].x(), pos.y() - self._points[0].y())
            <= CLOSE_DISTANCE
        ):
            self.finish()
            return True
        self._points.append(pos)
        self._cursor = QPointF(pos)
        if self._step is _Step.IDLE:
            self._begin_freeform()
        self._update_preview()
        self._show_drawing_feedback(event)
        return True

    def _begin_freeform(self) -> None:
        assert self._scene is not None
        self._step = _Step.PLACING
        item = PolygonItem()
        item.apply_creation_defaults(self._creation_defaults)
        item.polygon_mode = PolygonMode.FREEFORM
        item.closed = False  # the preview is the open path; the dashed line shows the close
        item.setPos(self._points[0])
        self._scene.addItem(item)
        self._item = item
        closing = QGraphicsPathItem()
        pen = QPen(QColor(0, 0, 0, 90), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        closing.setPen(pen)
        closing.setZValue(999990)
        self._scene.addItem(closing)
        self._closing = closing

    def _update_preview(self) -> None:
        item = self._item
        if item is None or not self._points:
            return
        origin = self._points[0]
        item.vertices = [p - origin for p in [*self._points, self._cursor]]
        if self._closing is not None:
            path = QPainterPath()
            if len(self._points) >= 2 and bool(self._creation_defaults.get("closed", True)):
                path.moveTo(self._cursor)
                path.lineTo(origin)
            self._closing.setPath(path)
        self._show_hint()

    def _begin_regular(self, center: QPointF) -> None:
        assert self._scene is not None
        self._step = _Step.DRAGGING
        self._center = QPointF(center)
        item = PolygonItem()
        item.apply_creation_defaults(self._creation_defaults)
        item.polygon_mode = PolygonMode.REGULAR
        item.closed = True
        item.regular_geometry = (QPointF(0, 0), 0.0, -90.0)
        item.setPos(center)
        self._scene.addItem(item)
        self._item = item
        self._show_hint()

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._step is _Step.PLACING:
            self._cursor = self._placed(event)
            self._update_preview()
            self._show_drawing_feedback(event)
            return True
        if self._step is _Step.DRAGGING and self._item is not None:
            pos = self._scene_pos(event)
            dx, dy = pos.x() - self._center.x(), pos.y() - self._center.y()
            angle = math.degrees(math.atan2(dy, dx))
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                angle = round(angle / 15.0) * 15.0
            self._item.regular_geometry = (QPointF(0, 0), math.hypot(dx, dy), angle)
            self._show_hint()
            self._show_drawing_feedback(event)
            return True
        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._step is _Step.DRAGGING:
            item = self._item
            if item is None or (item.radius or 0.0) < MIN_RADIUS:
                self.cancel()
            else:
                self._add(item)
            return True
        return self._step is _Step.PLACING

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        if self._step is _Step.PLACING:
            # The double-click's first press placed the final vertex (8.2)
            self.finish()
            return True
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if self._step is _Step.PLACING and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish()
            return True
        if event.key() == Qt.Key.Key_Escape:
            return self.handle_escape()
        return False

    def context_menu(self, event: QContextMenuEvent) -> bool:
        """No menu while vertices are placed: the right-click removes one (8.2)."""
        return self._step is _Step.PLACING

    def handle_escape(self) -> bool:
        """Escape cancels the polygon in progress (8.2)."""
        if self._step is _Step.IDLE:
            return False
        self.cancel()
        return True

    def finish(self) -> None:
        """Close the freeform polygon from the placed vertices; too few cancel it (8.2)."""
        item = self._item
        closed = bool(self._creation_defaults.get("closed", True))
        minimum = 3 if closed else 2
        if item is None or len(self._points) < minimum:
            self.cancel()
            return
        origin = self._points[0]
        item.vertices = [p - origin for p in self._points]
        item.closed = closed
        self._add(item)

    def _add(self, item: PolygonItem) -> None:
        self._hide_drawing_feedback()
        scene = self._scene
        self._remove_closing()
        self._item = None
        self._points = []
        self._step = _Step.IDLE
        if scene is None:
            return
        scene.removeItem(item)
        layer = scene.layer_manager.active_layer
        if layer is not None:
            scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
            if self._selection_manager is not None:
                self._selection_manager.select(item)
            self._switch_to_select()

    def _remove_closing(self) -> None:
        if self._closing is not None and self._closing.scene() is not None:
            self._closing.scene().removeItem(self._closing)  # type: ignore[union-attr]
        self._closing = None

    def cancel(self) -> None:
        self._hide_drawing_feedback()
        self._remove_closing()
        if self._item is not None and self._item.scene() is not None and self._scene is not None:
            self._scene.removeItem(self._item)
        self._item = None
        self._points = []
        self._step = _Step.IDLE
        self._show_hint()

    def deactivate(self) -> None:
        self.cancel()
        super().deactivate()
