"""FreehandTool — click-and-drag to draw freehand paths.

Basic Shape PRD Section 9. The Tool Options Bar of 9.6: the shared set of 2.6, with Fill
Color and Fill Opacity since a closed stroke fills (9.8), the Smoothing slider, then the
tool's own Stroke Cap toggles and Close Path toggle. On release the two-stage pipeline of
9.3 runs on the raw points (Basic Shape remainder decision 2, option A), and Close Path
joins the last point to the first.

The cursor (Freehand remainder decision 1, option A): 9.1's crosshair with a centre dot
while idle, and from the press to the release 9.2's brush tip, a filled circle at the
stroke's width times the zoom in the stroke's colour at its opacity, which follows the
bar and the zoom while the stroke is drawn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QIcon, QMouseEvent
from PyQt6.QtWidgets import QButtonGroup, QLabel, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_FILL_COLOR,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    BorderStyle,
    StrokeCap,
)
from snapmock.core.path_utils import constrain_angle
from snapmock.items.freehand_item import FreehandItem, PreviewSnapshot
from snapmock.items.vector_item import with_alpha
from snapmock.tools.base_tool import BaseTool
from snapmock.tools.highlight_tool import cap_icon
from snapmock.ui.cursors import brush_tip_cursor, dot_crosshair_cursor

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager

_CAP_STYLES: tuple[tuple[StrokeCap, str, str], ...] = (
    (StrokeCap.FLAT, "Flat", "Flat cap: the stroke ends at its endpoints"),
    (StrokeCap.ROUND, "Round", "Round cap: a half-circle beyond each endpoint"),
    (StrokeCap.SQUARE, "Square", "Square cap: a half-square beyond each endpoint"),
)
_CONTROL_HEIGHT = 26
MIN_STROKE_EXTENT = 2.0
"""A stroke whose points span less than this in both directions is an accidental click."""
DRAWING_STATE = "Drawing…"
"""9.11's Drawing row names a state rather than a measurement, and the tooltip shows the
same, so the tooltip and the hint agree (notes Section 9)."""
STRAIGHT_SEGMENT_DEGREES = 45.0
"""9.5: a Shift-held segment follows horizontal, vertical, or 45-degree diagonal lines."""
_CURSOR_KEYS = ("stroke_width", "stroke_color", "stroke_opacity")
"""The creation defaults the brush-tip cursor is drawn from (9.2)."""


class FreehandTool(BaseTool):
    """Interactive tool for freehand drawing."""

    # Tool Options Bar shared controls (Basic Shape PRD 2.6, 9.6; General UI PRD 5.3)
    options_controls = (
        "stroke_color",
        "fill_color",
        "stroke_width",
        "stroke_style",
        "fill_opacity",
        "stroke_opacity",
        "shadow_enabled",
        "smoothing",
    )

    def __init__(self) -> None:
        super().__init__()
        self._cap_buttons: dict[StrokeCap, QToolButton] = {}
        # 9.5: the stroke as it stood when Shift was first held, and the point the
        # straight segment runs from. None while the stroke follows the cursor freehand
        self._straight_from: PreviewSnapshot | None = None
        self._straight_anchor: QPointF | None = None
        self._close_button: QToolButton | None = None
        # The view whose zoom_changed the cursor follows while the tool is active
        self._zoom_view: Any = None
        self._creation_defaults = {
            "stroke_color": QColor(DEFAULT_STROKE_COLOR),
            "fill_color": QColor(DEFAULT_FILL_COLOR),
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "stroke_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "shadow_enabled": False,
            # Read by the Tool Options Bar's Smoothing slider (General UI PRD 5.2): a whole
            # percent, as presets store it; the item takes the fraction (notes Section 2.4)
            "smoothing": 50,
            "stroke_cap": StrokeCap.ROUND,
            "close_path": False,
        }

    @property
    def tool_id(self) -> str:
        return "freehand"

    @property
    def display_name(self) -> str:
        return "Freehand"

    @property
    def cursor(self) -> QCursor:
        """9.1's dot-variant crosshair while idle; 9.2's brush tip while a stroke is drawn:
        a filled circle ``stroke_width`` times the zoom across, in ``stroke_color`` at
        ``stroke_opacity`` (General UI PRD 6.6; Freehand remainder decision 1)."""
        if self._item is None:
            return dot_crosshair_cursor()
        view = self._view
        zoom = (view.zoom_percent / 100.0) if view is not None else 1.0
        width = float(self._creation_defaults.get("stroke_width", DEFAULT_STROKE_WIDTH))
        color = QColor(self._creation_defaults.get("stroke_color", DEFAULT_STROKE_COLOR))
        opacity = float(self._creation_defaults.get("stroke_opacity", 1.0))
        return brush_tip_cursor(round(width * zoom), with_alpha(color, opacity))

    def _refresh_cursor(self) -> None:
        """Put the tool's cursor back on the viewport: at the press, at the end of the
        stroke, and when the bar or the zoom changes the brush tip's size or colour."""
        view = self._view
        if view is not None:
            view.set_hover_cursor(self.cursor)

    def _on_zoom_changed(self, _percent: int) -> None:
        if self._item is not None:
            self._refresh_cursor()

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        view = self._view
        if view is not None:
            view.zoom_changed.connect(self._on_zoom_changed)
            self._zoom_view = view

    def deactivate(self) -> None:
        if self._zoom_view is not None:
            try:
                self._zoom_view.zoom_changed.disconnect(self._on_zoom_changed)
            except (TypeError, RuntimeError):
                pass  # the view is gone, or was never connected
            self._zoom_view = None
        super().deactivate()

    def _end_preview(self) -> None:
        """The stroke is over, by a release, a cancel, or Escape: the crosshair comes back."""
        super()._end_preview()
        self._refresh_cursor()

    @property
    def status_hint(self) -> str:
        """9.11's Idle and Drawing rows; the Drawing row's state is the tooltip's."""
        if self._item is not None:
            return f"{DRAWING_STATE} Shift: straight segments. Release to finish."
        return "Click and drag to draw a freehand stroke. Shift: constrain to straight segments."

    # ------------------------------------------------------------ the options bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Stroke Cap toggles and the Close Path toggle (PRD 9.6)."""
        toolbar.addWidget(QLabel(" Cap:"))
        group = QButtonGroup(toolbar)
        group.setExclusive(True)
        self._cap_buttons = {}
        for cap, name, tip in _CAP_STYLES:
            button = QToolButton()
            button.setCheckable(True)
            button.setIcon(QIcon(cap_icon(cap)))
            button.setToolTip(tip)
            button.setAccessibleName(f"{name} cap")
            button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
            button.toggled.connect(lambda checked, c=cap: self._on_cap_toggled(c, checked))
            group.addButton(button)
            toolbar.addWidget(button)
            self._cap_buttons[cap] = button
        close = QToolButton()
        close.setCheckable(True)
        close.setText("Close Path")
        close.setToolTip("Close Path: the stroke's last point joins its first on release")
        close.setAccessibleName("Close path")
        close.setMaximumHeight(_CONTROL_HEIGHT)
        close.toggled.connect(self._on_close_toggled)
        toolbar.addWidget(close)
        self._close_button = close
        self._sync_buttons()

    @property
    def cap_buttons(self) -> dict[StrokeCap, QToolButton]:
        return dict(self._cap_buttons)

    @property
    def close_path_button(self) -> QToolButton | None:
        return self._close_button

    def _sync_buttons(self) -> None:
        current = self._creation_defaults.get("stroke_cap", StrokeCap.ROUND)
        for cap, button in self._cap_buttons.items():
            button.blockSignals(True)
            button.setChecked(cap is current)
            button.blockSignals(False)
        if self._close_button is not None:
            self._close_button.blockSignals(True)
            self._close_button.setChecked(bool(self._creation_defaults.get("close_path")))
            self._close_button.blockSignals(False)

    def _announce(self) -> None:
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def _on_cap_toggled(self, cap: StrokeCap, checked: bool) -> None:
        if not checked:
            return
        self._creation_defaults["stroke_cap"] = cap
        self._announce()

    def _on_close_toggled(self, checked: bool) -> None:
        self._creation_defaults["close_path"] = bool(checked)
        self._announce()

    def on_option_changed(self, key: str, value: Any) -> None:
        if key in ("stroke_cap", "close_path"):
            self._sync_buttons()
        elif key in _CURSOR_KEYS and self._item is not None:
            self._refresh_cursor()

    # ------------------------------------------------------------ drawing

    def _scene_pos(self, event: QMouseEvent) -> QPointF:
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0].mapToScene(event.pos())
        return QPointF()

    @property
    def _item(self) -> FreehandItem | None:
        """The stroke being drawn: the shared drawing preview, typed."""
        item = self._preview_item
        return item if isinstance(item, FreehandItem) else None

    @property
    def drawing_measurement(self) -> tuple[str, ...]:
        """The Freehand's state while a stroke is drawn (2.4, 9.11)."""
        return (DRAWING_STATE,) if self._item is not None else ()

    def _drawing_bounds(self) -> QRectF | None:
        item = self._item
        return item.mapRectToScene(item.path.boundingRect()) if item is not None else None

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        pos = self._scene_pos(event)
        item = FreehandItem()
        item.apply_creation_defaults(self._creation_defaults)
        item.is_closed = False  # Close Path joins the ends on release (9.6)
        item.setPos(pos)
        item.add_point(QPointF(0, 0))
        self._straight_from = None
        self._straight_anchor = None
        self._start_preview(item)
        self._refresh_cursor()  # 9.2: the brush tip from the press
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        item = self._item
        if item is None or self._scene is None:
            return False
        local = self._scene_pos(event) - item.pos()
        if not self.constrains(event.modifiers()):
            # Freehand again: the straight segment, if there was one, keeps its end point
            self._straight_from = None
            self._straight_anchor = None
            item.add_point(local)
            self._show_drawing_feedback(event)
            return True
        # 9.5: one straight segment from where Shift was first held, replaced on every
        # move, so a curve and a straight run mix in one stroke
        if self._straight_from is None or self._straight_anchor is None:
            self._straight_from = item.preview_snapshot()
            self._straight_anchor = self._straight_from[0][-1]
        else:
            item.restore_preview(self._straight_from)
        item.add_point(constrain_angle(self._straight_anchor, local, STRAIGHT_SEGMENT_DEGREES))
        self._show_drawing_feedback(event)
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        created_item = self._item
        if created_item is None or self._scene is None:
            return False
        self._end_preview()
        self._straight_from = None
        self._straight_anchor = None
        points = created_item.path_points
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        big_enough = len(points) >= 2 and (
            max(xs) - min(xs) >= MIN_STROKE_EXTENT or max(ys) - min(ys) >= MIN_STROKE_EXTENT
        )
        if not big_enough:
            return True
        created_item.is_closed = bool(self._creation_defaults.get("close_path", False))
        created_item.smooth(float(self._creation_defaults.get("smoothing", 50)) / 100.0)
        layer = self._scene.layer_manager.active_layer
        if layer is not None:
            # 2.1, 2.5: the tool stays active and the new stroke is not selected (decision 2)
            cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
            self._scene.command_stack.push(cmd)
        return True
