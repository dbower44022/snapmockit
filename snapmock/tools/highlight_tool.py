"""HighlightTool — click-and-drag to draw highlight strokes.

Blur, Highlighter & Eyedropper PRD Section 3. The Tool Options Bar per 3.5: Highlight
Color, Stroke Width (10 to 80 px), Blend Mode, Stroke Style, then the tool's own Cap Style
toggles, the Auto-Straighten and Snap to Axis toggles, and the six preset colour swatches,
and the shared Shadow toggle. The colour's alpha is the opacity (3.7), so there is no
opacity control.

Drawing (3.2): the raw points are smoothed by a moving average over the last five while
the stroke is drawn, and simplified with Ramer-Douglas-Peucker at 2 px on release; a stroke
under 4 px long is an accidental click. Straightening (3.3): on release an approximately
straight stroke, whose arc length is within ``straighten_threshold`` of its straight-line
distance, becomes a single line; Shift forces a straight line from the press point to the
cursor at whatever angle, Shift+Alt constrains that to 15-degree steps, and a straightened
stroke within 5 degrees of an axis snaps onto it. All of it acts while the stroke is drawn
and never retroactively (3.6).
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QCursor, QIcon, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QButtonGroup, QLabel, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    DEFAULT_HIGHLIGHT_BLEND_MODE,
    DEFAULT_HIGHLIGHT_COLOR,
    DEFAULT_HIGHLIGHT_WIDTH,
    DEFAULT_STRAIGHTEN_THRESHOLD,
    HIGHLIGHT_MIN_LENGTH,
    HIGHLIGHT_PRESET_COLORS,
    HIGHLIGHT_SIMPLIFY_EPSILON,
    HIGHLIGHT_SMOOTHING_WINDOW,
    SNAP_TO_AXIS_DEGREES,
    BorderStyle,
    StrokeCap,
)
from snapmock.core.path_utils import (
    constrain_angle,
    moving_average,
    path_length,
    simplify_rdp,
    snap_to_axis,
    straightness,
)
from snapmock.items.highlight_item import HighlightItem
from snapmock.tools.base_tool import BaseTool

_CAP_STYLES: tuple[tuple[StrokeCap, str, str], ...] = (
    (StrokeCap.FLAT, "Flat", "Flat cap: the band ends at the endpoint"),
    (StrokeCap.ROUND, "Round", "Round cap: a half-circle beyond the endpoint"),
    (StrokeCap.SQUARE, "Square", "Square cap: a half-square beyond the endpoint"),
)
_SWATCH = 16
_CONTROL_HEIGHT = 26


def cap_icon(cap: StrokeCap, size: int = 16) -> QPixmap:
    """A short stroke drawn with *cap*, the toggle's preview icon (PRD 3.5)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = painter.pen()
    pen.setColor(QColor(90, 90, 90))
    pen.setWidth(max(4, size // 3))
    pen.setCapStyle(
        {
            StrokeCap.FLAT: Qt.PenCapStyle.FlatCap,
            StrokeCap.ROUND: Qt.PenCapStyle.RoundCap,
            StrokeCap.SQUARE: Qt.PenCapStyle.SquareCap,
        }[cap]
    )
    painter.setPen(pen)
    painter.drawLine(QPointF(size * 0.3, size / 2), QPointF(size * 0.7, size / 2))
    painter.end()
    return pixmap


class HighlightTool(BaseTool):
    """Interactive tool for drawing highlight strokes."""

    options_controls = (
        "highlight_color",
        "highlight_width",
        "blend_mode",
        "stroke_style",
        "tool",
        "shadow_enabled",
    )

    def __init__(self) -> None:
        super().__init__()
        self._item: HighlightItem | None = None
        self._creation_defaults = {
            "highlight_color": QColor(DEFAULT_HIGHLIGHT_COLOR),
            "highlight_width": DEFAULT_HIGHLIGHT_WIDTH,
            "blend_mode": DEFAULT_HIGHLIGHT_BLEND_MODE,
            "stroke_style": BorderStyle.SOLID,
            "stroke_cap": StrokeCap.FLAT,
            "auto_straighten": True,
            "straighten_threshold": DEFAULT_STRAIGHTEN_THRESHOLD,
            "snap_to_axis": True,
            "shadow_enabled": False,
        }
        self._cap_buttons: dict[StrokeCap, QToolButton] = {}
        self._cap_group: QButtonGroup | None = None
        self._swatches: list[QToolButton] = []
        self._toolbar: QToolBar | None = None
        self._straighten_button: QToolButton | None = None
        self._snap_button: QToolButton | None = None
        self._raw: list[QPointF] = []
        self._origin = QPointF()
        self._shift = False

    @property
    def tool_id(self) -> str:
        return "highlight"

    @property
    def display_name(self) -> str:
        return "Highlight"

    @property
    def cursor(self) -> Qt.CursorShape | QCursor:
        """The angled marker tip (3.1; General UI PRD 6.6, a row this work adds)."""
        from snapmock.ui.cursors import marker_tip_cursor

        return marker_tip_cursor()

    @property
    def is_active_operation(self) -> bool:
        return self._item is not None

    @property
    def preview(self) -> HighlightItem | None:
        return self._item

    @property
    def status_hint(self) -> str:
        """The hints of 3.9."""
        if self._item is not None:
            if self._shift:
                return "Straight highlight. Release to finish."
            return "Highlighting... Release to finish. Shift: force straight."
        state = "ON" if self._creation_defaults.get("auto_straighten", True) else "OFF"
        return f"Click and drag to highlight. Shift: straight line. Auto-straighten: {state}."

    def _show_hint(self) -> None:
        window = self._window()
        show = getattr(window, "show_status_hint", None)
        if callable(show):
            show(self.status_hint)

    # ------------------------------------------------------------ the bar

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """The Cap Style toggles and the six preset colour swatches (PRD 3.5)."""
        self._toolbar = toolbar
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
        self._cap_group = group
        self._straighten_button = self._toggle(
            toolbar,
            "ruler",
            "Auto-Straighten",
            "Auto-Straighten: an approximately straight stroke becomes a line",
            "auto_straighten",
        )
        self._snap_button = self._toggle(
            toolbar,
            "magnet",
            "Snap to Axis",
            "Snap to Axis: a straightened stroke near horizontal or vertical snaps to it",
            "snap_to_axis",
        )
        toolbar.addWidget(QLabel(" Presets:"))
        self._swatches = []
        for name, argb in HIGHLIGHT_PRESET_COLORS:
            swatch = QToolButton()
            pixmap = QPixmap(_SWATCH, _SWATCH)
            pixmap.fill(QColor(argb))
            swatch.setIcon(QIcon(pixmap))
            swatch.setToolTip(f"{name} highlight")
            swatch.setAccessibleName(f"{name} preset colour")
            swatch.setFixedSize(_CONTROL_HEIGHT - 4, _CONTROL_HEIGHT - 4)
            swatch.clicked.connect(lambda _c=False, a=argb: self._on_swatch_clicked(QColor(a)))
            toolbar.addWidget(swatch)
            self._swatches.append(swatch)
        self._sync_cap_buttons()

    def _toggle(self, toolbar: QToolBar, glyph: str, name: str, tip: str, key: str) -> QToolButton:
        """One of the two straightening toggles of 3.5, with its Tabler glyph."""
        from snapmock.core.theme_manager import theme_manager

        button = QToolButton()
        button.setCheckable(True)
        button.setIcon(theme_manager().icon(glyph))
        button.setToolTip(tip)
        button.setAccessibleName(name)
        button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
        button.setChecked(bool(self._creation_defaults.get(key, True)))
        button.toggled.connect(lambda checked, k=key: self._on_toggle(k, bool(checked)))
        toolbar.addWidget(button)
        return button

    def _on_toggle(self, key: str, checked: bool) -> None:
        self._creation_defaults[key] = checked
        self._announce()
        self._show_hint()

    @property
    def straighten_button(self) -> QToolButton | None:
        return self._straighten_button

    @property
    def snap_button(self) -> QToolButton | None:
        return self._snap_button

    @property
    def cap_buttons(self) -> dict[StrokeCap, QToolButton]:
        return dict(self._cap_buttons)

    @property
    def preset_swatches(self) -> list[QToolButton]:
        return list(self._swatches)

    def _sync_cap_buttons(self) -> None:
        current = self._creation_defaults.get("stroke_cap", StrokeCap.FLAT)
        for cap, button in self._cap_buttons.items():
            button.blockSignals(True)
            button.setChecked(cap is current)
            button.blockSignals(False)

    def _announce(self) -> None:
        window = self._window()
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def _on_cap_toggled(self, cap: StrokeCap, checked: bool) -> None:
        if not checked:
            return
        self._creation_defaults["stroke_cap"] = cap
        self._announce()

    def _on_swatch_clicked(self, color: QColor) -> None:
        self._creation_defaults["highlight_color"] = QColor(color)
        self._announce()

    def on_option_changed(self, key: str, value: Any) -> None:
        if key == "stroke_cap":
            self._sync_cap_buttons()
        elif key in ("auto_straighten", "snap_to_axis"):
            button = self._straighten_button if key == "auto_straighten" else self._snap_button
            if button is not None:
                button.blockSignals(True)
                button.setChecked(bool(value))
                button.blockSignals(False)
            self._show_hint()

    def _window(self) -> Any:
        view = self._view
        return view.window() if view is not None else None

    # ------------------------------------------------------------ drawing

    def _scene_pos(self, event: QMouseEvent) -> QPointF:
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0].mapToScene(event.pos())
        return QPointF()

    def _item_defaults(self) -> dict[str, Any]:
        """The creation defaults under the item's key names."""
        d = dict(self._creation_defaults)
        d["stroke_color"] = QColor(d.pop("highlight_color", QColor(DEFAULT_HIGHLIGHT_COLOR)))
        d["stroke_width"] = float(d.pop("highlight_width", DEFAULT_HIGHLIGHT_WIDTH))
        return d

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.layer_allows_drawing():
            return True
        pos = self._scene_pos(event)
        self._origin = QPointF(pos)
        self._raw = [QPointF(0, 0)]
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self._item = HighlightItem()
        self._item.apply_creation_defaults(self._item_defaults())
        self._item.setPos(pos)
        self._item.set_points([(0.0, 0.0)])
        self._scene.addItem(self._item)
        self._show_hint()
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._item is None or self._scene is None:
            return False
        local = self._scene_pos(event) - self._origin
        self._raw.append(QPointF(local))
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self._item.set_points([(p.x(), p.y()) for p in self._drawn_points(event.modifiers())])
        self._show_hint()
        return True

    def _drawn_points(self, modifiers: Qt.KeyboardModifier) -> list[QPointF]:
        """What the stroke looks like right now: a straight line while Shift is held, and
        the moving average of the raw points otherwise (3.2, 3.3)."""
        if not self._raw:
            return []
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            end = self._raw[-1]
            if modifiers & Qt.KeyboardModifier.AltModifier:
                # Shift+Alt constrains the straight highlight to 15-degree steps (3.3)
                end = constrain_angle(self._raw[0], end)
            return [QPointF(self._raw[0]), end]
        return moving_average(self._raw, HIGHLIGHT_SMOOTHING_WINDOW)

    def finish_points(self, modifiers: Qt.KeyboardModifier) -> list[QPointF]:
        """The stroke as it is placed: straightened if it should be, then simplified (3.2).

        Shift forces the straight line at whatever angle; otherwise an approximately
        straight stroke, within ``straighten_threshold`` of its straight-line distance, is
        replaced by a line from its first point to its last. A straightened stroke within
        five degrees of an axis snaps onto it, which is a correction applied only to a
        stroke that is already a line (3.3).
        """
        points = self._drawn_points(modifiers)
        if len(points) < 2:
            return points
        forced = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        auto = bool(self._creation_defaults.get("auto_straighten", True))
        threshold = float(
            self._creation_defaults.get("straighten_threshold", DEFAULT_STRAIGHTEN_THRESHOLD)
        )
        straight = forced or (auto and straightness(points) < threshold)
        if straight:
            start, end = points[0], points[-1]
            if self._creation_defaults.get("snap_to_axis", True):
                end = snap_to_axis(start, end, SNAP_TO_AXIS_DEGREES)
            return [QPointF(start), QPointF(end)]
        return simplify_rdp(points, HIGHLIGHT_SIMPLIFY_EPSILON)

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._item is None or self._scene is None:
            return False
        self._scene.removeItem(self._item)
        created_item = self._item
        self._item = None
        self._shift = False
        points = self.finish_points(event.modifiers())
        self._raw = []
        # A stroke under 4 px long is an accidental click (3.2)
        if len(points) >= 2 and path_length(points) >= HIGHLIGHT_MIN_LENGTH:
            created_item.set_points([(p.x(), p.y()) for p in points])
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                if self._selection_manager is not None:
                    self._selection_manager.select(created_item)
                self._switch_to_select()
        self._show_hint()
        return True

    def cancel(self) -> None:
        if self._item is not None and self._scene is not None and self._item.scene() is not None:
            self._scene.removeItem(self._item)
        self._item = None
        self._raw = []
        self._shift = False
