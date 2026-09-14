"""BlurTool — click-and-drag to create blur regions (Blur PRD Section 2).

The drag draws a rectangle or an ellipse region (2.3, 2.4), Shift constraining it to a
square or a circle and Alt drawing from the centre, with the effect shown live beneath it;
a region under 16 square pixels is an accidental click.

A Freeform region is painted instead: press and drag to paint into the region's alpha mask
with a round brush ``brush_size`` pixels across, Shift holding the stroke straight from the
press point; strokes accumulate into one region, Enter or a tool switch finalizes it,
Escape drops it, and a region with nothing painted is dropped too (2.3). The region's
rectangle follows the painted bounds, and the mask is kept in canvas pixels, so paint
outside the canvas is clipped away.

The Tool Options Bar of 2.6: the Blur Mode toggles, the intensity slider whose label
follows the mode (Blur Radius 1 to 50, Pixel Size 2 to 100, hidden for Solid Fill), Fill
Color for Solid Fill, the Region Shape toggles (Rectangle, Ellipse, Freeform), Corner
Radius for a rectangle, Feather, Brush Size for a Freeform region, Invert Mask, and
Opacity. Whole Layer joins the Region Shape group as a fourth toggle, which 2.6's three do
not list: without it the shape of 2.4 could not be created at all. One click places it and
its region is the canvas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QCursor, QImage, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QButtonGroup, QLabel, QSlider, QSpinBox, QToolBar, QToolButton

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    BLUR_BRUSH_SIZE_MAX,
    BLUR_BRUSH_SIZE_MIN,
    BLUR_FEATHER_MAX,
    BLUR_PIXEL_SIZE_MAX,
    BLUR_PIXEL_SIZE_MIN,
    BLUR_RADIUS_MAX,
    BLUR_RADIUS_MIN,
    CORNER_RADIUS_MAX,
    DEFAULT_BLUR_BRUSH_SIZE,
    DEFAULT_BLUR_FILL_COLOR,
    BlurMode,
    BlurRegionShape,
)
from snapmock.items.blur_item import BlurItem
from snapmock.items.mask_utils import blank_mask, paint_stroke, painted_bounds, restore_region
from snapmock.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager

MIN_AREA = 16.0
"""A region under this many square pixels is an accidental click (2.3)."""

_MODES: tuple[tuple[BlurMode, str], ...] = (
    (BlurMode.GAUSSIAN, "Gaussian Blur"),
    (BlurMode.PIXELATE, "Pixelate"),
    (BlurMode.SOLID, "Solid Fill"),
)
_SHAPES: tuple[tuple[BlurRegionShape, str], ...] = (
    (BlurRegionShape.RECTANGLE, "Rectangle"),
    (BlurRegionShape.ELLIPSE, "Ellipse"),
    (BlurRegionShape.FREEFORM, "Freeform"),
    (BlurRegionShape.WHOLE_LAYER, "Whole Layer"),
)
_CONTROL_HEIGHT = 26


class BlurTool(BaseTool):
    """Interactive tool for creating blur regions."""

    def __init__(self) -> None:
        super().__init__()
        self._start: QPointF = QPointF()
        self._item: BlurItem | None = None
        self._mode_buttons: dict[BlurMode, QToolButton] = {}
        self._shape_buttons: dict[BlurRegionShape, QToolButton] = {}
        self._intensity_label: QLabel | None = None
        self._intensity_slider: QSlider | None = None
        self._intensity_spin: QSpinBox | None = None
        self._fill_picker: Any = None
        self._corner_spin: QSpinBox | None = None
        self._feather_spin: QSpinBox | None = None
        self._invert_button: QToolButton | None = None
        self._brush_spin: QSpinBox | None = None
        self._opacity_spin: QSpinBox | None = None
        self._paint_mask: QImage | None = None
        self._stroke_base: QImage | None = None
        self._paint_bounds = QRectF()
        self._stroke_bounds = QRectF()
        self._straight_bounds = QRectF()
        self._last_point: QPointF | None = None
        self._stroke_start: QPointF | None = None
        # The view whose zoom_changed the brush cursor follows while the tool is active
        self._zoom_view: Any = None
        self._groups: dict[str, list[QAction]] = {}
        self._syncing = False
        self._creation_defaults = {
            "blur_mode": BlurMode.GAUSSIAN,
            "region_shape": BlurRegionShape.RECTANGLE,
            "blur_radius": 10.0,
            "pixel_size": 10,
            "fill_color": QColor(DEFAULT_BLUR_FILL_COLOR),
            "corner_radius": 0.0,
            "feather": 0.0,
            "invert_mask": False,
            "brush_size": DEFAULT_BLUR_BRUSH_SIZE,
            "opacity": 1.0,
        }

    @property
    def tool_id(self) -> str:
        return "blur"

    @property
    def display_name(self) -> str:
        return "Blur"

    @property
    def cursor(self) -> Qt.CursorShape | QCursor:
        """The crosshair, or a circle at the brush's size while the shape is Freeform
        (General UI PRD 6.6; Blur PRD 2.6)."""
        if self._creation_defaults.get("region_shape") is not BlurRegionShape.FREEFORM:
            return Qt.CursorShape.CrossCursor
        from snapmock.ui.cursors import brush_cursor

        view = self._view
        zoom = (view.zoom_percent / 100.0) if view is not None else 1.0
        return brush_cursor(round(self.brush_size * zoom))

    @property
    def brush_size(self) -> float:
        """The brush's diameter in scene pixels, 5 to 200 (2.5)."""
        raw = self._creation_defaults.get("brush_size", DEFAULT_BLUR_BRUSH_SIZE)
        return max(BLUR_BRUSH_SIZE_MIN, min(BLUR_BRUSH_SIZE_MAX, float(raw)))

    def _refresh_cursor(self) -> None:
        """Put the tool's cursor back on the viewport after the brush or the shape moved."""
        view = self._view
        if view is not None:
            view.set_hover_cursor(self.cursor)

    @property
    def freeform(self) -> bool:
        return self._creation_defaults.get("region_shape") is BlurRegionShape.FREEFORM

    @property
    def is_active_operation(self) -> bool:
        """A live drag or a live brush stroke; an unfinalized Freeform region between
        strokes is not one, so a focus change or Ctrl+Z does not disturb it."""
        if self._paint_mask is not None:
            return self._last_point is not None
        return self._item is not None

    @property
    def painting(self) -> bool:
        """True while a Freeform region is being painted, finalized or not."""
        return self._paint_mask is not None

    @property
    def preview(self) -> BlurItem | None:
        return self._item

    @property
    def status_hint(self) -> str:
        """The hints of 2.11."""
        item = self._item
        if self._paint_mask is not None:
            if self._last_point is not None:
                return "Painting blur area. Release and continue, or Enter to finish."
            return "Paint to define blur area. Enter: finish. Shift: straight strokes."
        if item is None:
            if self.freeform:
                return "Paint to define blur area. Enter: finish. Shift: straight strokes."
            if self._creation_defaults.get("region_shape") is BlurRegionShape.WHOLE_LAYER:
                return "Click to blur the whole canvas."
            return "Click and drag to define blur region. Shift: constrain. Alt: from center."
        mode = dict(_MODES)[item.blur_mode]
        detail = ""
        if item.blur_mode is BlurMode.GAUSSIAN:
            detail = f" | Radius: {item.blur_radius:.0f}"
        elif item.blur_mode is BlurMode.PIXELATE:
            detail = f" | Pixel size: {item.pixel_size}"
        rect = item.rect
        return (
            f"W: {rect.width():.0f} H: {rect.height():.0f} | Mode: {mode}{detail} | "
            "Release to apply."
        )

    def _show_hint(self) -> None:
        view = self._view
        window = view.window() if view is not None else None
        show = getattr(window, "show_status_hint", None)
        if callable(show):
            show(self.status_hint)

    # ------------------------------------------------------------ the options bar (2.6)

    def _spin_slider(
        self, toolbar: QToolBar, label: str, low: int, high: int, suffix: str, key: str
    ) -> tuple[QLabel, QSlider, QSpinBox, list[QAction]]:
        text = QLabel(f" {label}:")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setFixedWidth(80)
        slider.setAccessibleName(f"{label} slider")
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setMaximumWidth(64)
        spin.setMaximumHeight(_CONTROL_HEIGHT)
        spin.setAccessibleName(label)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        spin.valueChanged.connect(lambda v, k=key: self._on_value(k, v))
        actions = [toolbar.addWidget(w) for w in (text, slider, spin)]
        return text, slider, spin, [a for a in actions if a is not None]

    def _toggles(
        self, toolbar: QToolBar, entries: tuple[tuple[Any, str], ...], suffix: str, key: str
    ) -> dict[Any, QToolButton]:
        group = QButtonGroup(toolbar)
        group.setExclusive(True)
        buttons: dict[Any, QToolButton] = {}
        for value, name in entries:
            button = QToolButton()
            button.setCheckable(True)
            button.setText(name)
            button.setToolTip(name)
            button.setAccessibleName(f"{name} {suffix}")
            button.setMaximumHeight(_CONTROL_HEIGHT)
            button.toggled.connect(
                lambda checked, v=value, k=key: self._on_value(k, v) if checked else None
            )
            group.addButton(button)
            toolbar.addWidget(button)
            buttons[value] = button
        return buttons

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        from snapmock.ui.color_picker import ColorPicker

        self._groups = {}
        toolbar.addWidget(QLabel(" Mode:"))
        self._mode_buttons = self._toggles(toolbar, _MODES, "mode", "blur_mode")
        label, slider, spin, actions = self._spin_slider(
            toolbar, "Blur Radius", int(BLUR_RADIUS_MIN), int(BLUR_RADIUS_MAX), " px", "intensity"
        )
        self._intensity_label, self._intensity_slider, self._intensity_spin = label, slider, spin
        self._groups["intensity"] = actions
        fill_label = toolbar.addWidget(QLabel(" Fill:"))
        picker = ColorPicker(swatch_size=24)
        picker.setToolTip("Fill colour for Solid Fill")
        picker.setAccessibleName("Fill color")
        picker.color_changed.connect(lambda c: self._on_value("fill_color", QColor(c)))
        fill_action = toolbar.addWidget(picker)
        self._fill_picker = picker
        self._groups["fill"] = [a for a in (fill_label, fill_action) if a is not None]
        toolbar.addWidget(QLabel(" Shape:"))
        self._shape_buttons = self._toggles(toolbar, _SHAPES, "region", "region_shape")
        _l, _s, self._corner_spin, actions = self._spin_slider(
            toolbar, "Corner Radius", 0, int(CORNER_RADIUS_MAX), " px", "corner_radius"
        )
        self._groups["corner"] = actions
        _l, _s, self._feather_spin, _a = self._spin_slider(
            toolbar, "Feather", 0, int(BLUR_FEATHER_MAX), " px", "feather"
        )
        _l, _s, self._brush_spin, actions = self._spin_slider(
            toolbar,
            "Brush Size",
            int(BLUR_BRUSH_SIZE_MIN),
            int(BLUR_BRUSH_SIZE_MAX),
            " px",
            "brush_size",
        )
        self._groups["brush"] = actions
        invert = QToolButton()
        invert.setCheckable(True)
        invert.setText("Invert")
        invert.setToolTip("Invert Mask: obscure everything outside the region")
        invert.setAccessibleName("Invert mask")
        invert.setMaximumHeight(_CONTROL_HEIGHT)
        invert.toggled.connect(lambda checked: self._on_value("invert_mask", bool(checked)))
        toolbar.addWidget(invert)
        self._invert_button = invert
        _l, _s, self._opacity_spin, _a = self._spin_slider(
            toolbar, "Opacity", 0, 100, "%", "opacity"
        )
        self._sync_controls()

    @property
    def mode_buttons(self) -> dict[BlurMode, QToolButton]:
        return dict(self._mode_buttons)

    @property
    def shape_buttons(self) -> dict[BlurRegionShape, QToolButton]:
        return dict(self._shape_buttons)

    @property
    def intensity_label(self) -> QLabel | None:
        return self._intensity_label

    @property
    def intensity_spin(self) -> QSpinBox | None:
        return self._intensity_spin

    @property
    def invert_button(self) -> QToolButton | None:
        return self._invert_button

    @property
    def brush_spin(self) -> QSpinBox | None:
        return self._brush_spin

    def control_actions(self) -> dict[str, list[QAction]]:
        return {k: list(v) for k, v in self._groups.items()}

    def _on_value(self, key: str, value: Any) -> None:
        if self._syncing:
            return
        d = self._creation_defaults
        if key == "intensity":
            if d.get("blur_mode") is BlurMode.PIXELATE:
                d["pixel_size"] = int(value)
            else:
                d["blur_radius"] = float(value)
        elif key == "opacity":
            d["opacity"] = int(value) / 100.0
        elif key in ("corner_radius", "feather", "brush_size"):
            d[key] = float(value)
        else:
            d[key] = value
        self._sync_controls()
        view = self._view
        window: Any = view.window() if view is not None else None
        manager = getattr(window, "tool_manager", None)
        if manager is not None:
            manager.tool_defaults_changed.emit(self.tool_id)

    def _sync_controls(self) -> None:
        """Show the controls the mode and the shape use, holding the defaults (2.6)."""
        d = self._creation_defaults
        mode = d.get("blur_mode", BlurMode.GAUSSIAN)
        shape = d.get("region_shape", BlurRegionShape.RECTANGLE)
        self._syncing = True
        try:
            for mode_value, button in self._mode_buttons.items():
                button.setChecked(mode_value is mode)
            for shape_value, button in self._shape_buttons.items():
                button.setChecked(shape_value is shape)
            if self._intensity_spin is not None and self._intensity_slider is not None:
                if mode is BlurMode.PIXELATE:
                    low, high = int(BLUR_PIXEL_SIZE_MIN), int(BLUR_PIXEL_SIZE_MAX)
                    value, label = int(d.get("pixel_size", 10)), "Pixel Size"
                else:
                    low, high = int(BLUR_RADIUS_MIN), int(BLUR_RADIUS_MAX)
                    value, label = int(round(float(d.get("blur_radius", 10.0)))), "Blur Radius"
                for widget in (self._intensity_spin, self._intensity_slider):
                    widget.setRange(low, high)
                    widget.setValue(value)
                self._intensity_spin.setAccessibleName(label)
                self._intensity_slider.setAccessibleName(f"{label} slider")
                if self._intensity_label is not None:
                    self._intensity_label.setText(f" {label}:")
            if self._fill_picker is not None:
                self._fill_picker.color = QColor(d.get("fill_color", DEFAULT_BLUR_FILL_COLOR))
            if self._corner_spin is not None:
                self._corner_spin.setValue(int(round(float(d.get("corner_radius", 0.0)))))
            if self._feather_spin is not None:
                self._feather_spin.setValue(int(round(float(d.get("feather", 0.0)))))
            if self._brush_spin is not None:
                self._brush_spin.setValue(
                    int(round(float(d.get("brush_size", DEFAULT_BLUR_BRUSH_SIZE))))
                )
            if self._invert_button is not None:
                self._invert_button.setChecked(bool(d.get("invert_mask")))
            if self._opacity_spin is not None:
                self._opacity_spin.setValue(int(round(float(d.get("opacity", 1.0)) * 100)))
        finally:
            self._syncing = False
        visible = {
            "intensity": mode is not BlurMode.SOLID,
            "fill": mode is BlurMode.SOLID,
            "corner": shape is BlurRegionShape.RECTANGLE,
            "brush": shape is BlurRegionShape.FREEFORM,
        }
        for group, actions in self._groups.items():
            for action in actions:
                action.setVisible(visible.get(group, True))
        self._refresh_cursor()

    def on_option_changed(self, key: str, value: Any) -> None:
        self._sync_controls()

    def _scene_pos(self, event: QMouseEvent) -> QPointF:
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0].mapToScene(event.pos())
        return QPointF()

    # ---------------------------------------------- the freeform brush (2.3, 2.11)

    def _begin_freeform(self) -> BlurItem | None:
        """Start a Freeform region: the working mask covers the canvas, so paint outside
        it is clipped away, and the item is in the scene but not yet committed."""
        scene = self._scene
        if scene is None:
            return None
        canvas = scene.canvas_rect
        self._paint_mask = blank_mask(round(canvas.width()), round(canvas.height()))
        self._paint_bounds = QRectF()
        item = BlurItem(rect=QRectF(0, 0, 0, 0))
        item.apply_creation_defaults(self._creation_defaults)
        item.region_shape = BlurRegionShape.FREEFORM
        scene.addItem(item)
        self._item = item
        return item

    def _refresh_freeform(self) -> None:
        """Put the painted bounds and the cropped mask on the item (2.3, 2.5)."""
        mask, item = self._paint_mask, self._item
        if mask is None or item is None:
            return
        bounds = self._paint_bounds.intersected(QRectF(0, 0, mask.width(), mask.height()))
        if bounds.isEmpty():
            item.setPos(0, 0)
            item.rect = QRectF(0, 0, 0, 0)
            item.alpha_mask = None
            return
        rect = bounds.toAlignedRect()
        item.setPos(rect.x(), rect.y())
        item.rect = QRectF(0, 0, rect.width(), rect.height())
        item.alpha_mask = mask.copy(QRect(rect))

    def _paint_segment(self, start: QPointF, end: QPointF) -> None:
        mask = self._paint_mask
        if mask is None:
            return
        covered = paint_stroke(mask, start, end, self.brush_size)
        self._stroke_bounds = (
            covered if self._stroke_bounds.isEmpty() else self._stroke_bounds.united(covered)
        )
        self._paint_bounds = (
            covered if self._paint_bounds.isEmpty() else self._paint_bounds.united(covered)
        )

    def _paint_press(self, pos: QPointF) -> bool:
        if self._paint_mask is None and self._begin_freeform() is None:
            return False
        mask = self._paint_mask
        assert mask is not None
        self._stroke_base = mask.copy()
        self._stroke_bounds = QRectF()
        self._straight_bounds = QRectF()
        self._stroke_start = QPointF(pos)
        self._last_point = QPointF(pos)
        self._paint_segment(pos, pos)
        self._refresh_freeform()
        self._show_hint()
        return True

    def _paint_move(self, pos: QPointF, modifiers: Qt.KeyboardModifier) -> bool:
        mask = self._paint_mask
        last = self._last_point
        if mask is None or last is None:
            return False
        if modifiers & Qt.KeyboardModifier.ShiftModifier and self._stroke_start is not None:
            # Shift holds the stroke straight from the press point: redraw it from the
            # mask as it stood when the stroke began (2.11)
            base = self._stroke_base
            if base is not None and not self._straight_bounds.isEmpty():
                restore_region(mask, base, self._straight_bounds)
                self._paint_bounds = painted_bounds(mask)
            self._stroke_bounds = QRectF()
            self._paint_segment(self._stroke_start, pos)
            self._straight_bounds = QRectF(self._stroke_bounds)
        else:
            self._paint_segment(last, pos)
            self._straight_bounds = QRectF()
        self._last_point = QPointF(pos)
        self._refresh_freeform()
        self._show_hint()
        return True

    def finish_freeform(self) -> None:
        """Commit the painted region, or drop it when nothing was painted (2.3)."""
        item, mask = self._item, self._paint_mask
        self._paint_mask = self._stroke_base = None
        self._last_point = self._stroke_start = None
        self._paint_bounds = self._stroke_bounds = self._straight_bounds = QRectF()
        self._item = None
        if item is None or self._scene is None:
            self._show_hint()
            return
        if item.scene() is not None:
            self._scene.removeItem(item)
        rect = item.rect
        layer = self._scene.layer_manager.active_layer
        if mask is None or item.alpha_mask is None or rect.isEmpty() or layer is None:
            self._show_hint()
            return
        # Basic Shape shared drawing decision 2: the tool stays active and the new region is
        # not selected, whichever of the three routes made it
        self._scene.command_stack.push(AddItemCommand(self._scene, item, layer.layer_id))
        self._show_hint()

    def discard_freeform(self) -> None:
        """Drop the region being painted, keeping nothing (Escape, 2.3)."""
        item = self._item
        if item is not None and self._scene is not None and item.scene() is not None:
            self._scene.removeItem(item)
        self._item = None
        self._paint_mask = self._stroke_base = None
        self._last_point = self._stroke_start = None
        self._paint_bounds = self._stroke_bounds = self._straight_bounds = QRectF()
        self._show_hint()

    def key_press(self, event: QKeyEvent) -> bool:
        """Enter finishes a painted region (2.3)."""
        if self._paint_mask is None:
            return False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_freeform()
            return True
        return False

    def handle_escape(self) -> bool:
        """Escape drops the region being painted (2.3)."""
        if self._paint_mask is None:
            return False
        self.discard_freeform()
        return True

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        view = self._view
        if view is not None:
            # The brush cursor is drawn in screen pixels, so it follows the zoom
            # (General UI PRD 6.6; found by the Freehand remainder work, 09-13-26)
            view.zoom_changed.connect(self._on_zoom_changed)
            self._zoom_view = view
        self._refresh_cursor()

    def deactivate(self) -> None:
        """A tool switch finalizes the painted region (2.3)."""
        if self._paint_mask is not None:
            self.finish_freeform()
        if self._zoom_view is not None:
            try:
                self._zoom_view.zoom_changed.disconnect(self._on_zoom_changed)
            except (TypeError, RuntimeError):
                pass  # the view is gone, or was never connected
            self._zoom_view = None
        super().deactivate()

    def _on_zoom_changed(self, _percent: int) -> None:
        if self.freeform:
            self._refresh_cursor()

    # ------------------------------------------------------------ drawing (2.3)

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False
        # 8.1: no region on a locked or hidden layer. A stroke that continues a region
        # already begun is not a new press in that sense, so the guard runs before it
        if self._paint_mask is None and not self.layer_allows_drawing():
            return True
        if self._paint_mask is not None or self.freeform:
            return self._paint_press(self._scene_pos(event))
        if self._creation_defaults.get("region_shape") is BlurRegionShape.WHOLE_LAYER:
            return self._place_whole_layer()
        self._start = self._snap_pos(self._scene_pos(event))
        self._item = BlurItem(rect=QRectF(0, 0, 0, 0))
        self._item.apply_creation_defaults(self._creation_defaults)
        self._item.setPos(self._start)
        self._scene.addItem(self._item)
        self._show_hint()
        return True

    def _place_whole_layer(self) -> bool:
        """One click places a Whole Layer region over the canvas; there is nothing to drag
        (2.4)."""
        scene = self._scene
        layer = scene.layer_manager.active_layer if scene is not None else None
        if scene is None or layer is None:
            return False
        canvas = scene.canvas_rect
        item = BlurItem(rect=QRectF(0, 0, canvas.width(), canvas.height()))
        item.apply_creation_defaults(self._creation_defaults)
        item.region_shape = BlurRegionShape.WHOLE_LAYER
        item.setPos(canvas.topLeft())
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))  # decision 2
        self._show_hint()
        return True

    def region_for(
        self, start: QPointF, current: QPointF, modifiers: Qt.KeyboardModifier
    ) -> QRectF:
        """The drawn region in scene coordinates: Shift makes a square or a circle, Alt
        draws from the centre (2.3)."""
        dx = current.x() - start.x()
        dy = current.y() - start.y()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            side = max(abs(dx), abs(dy))
            dx = side if dx >= 0 else -side
            dy = side if dy >= 0 else -side
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return QRectF(start.x() - abs(dx), start.y() - abs(dy), 2 * abs(dx), 2 * abs(dy))
        return QRectF(start, QPointF(start.x() + dx, start.y() + dy)).normalized()

    def mouse_move(self, event: QMouseEvent) -> bool:
        if self._paint_mask is not None:
            return self._paint_move(self._scene_pos(event), event.modifiers())
        if self._item is None or self._scene is None:
            return False
        current = self._snap_pos(self._scene_pos(event))
        rect = self.region_for(self._start, current, event.modifiers())
        self._item.setPos(rect.topLeft())
        self._item.rect = QRectF(0, 0, rect.width(), rect.height())
        self._show_hint()
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._paint_mask is not None:
            # The stroke ends; the region stays open for the next one (2.3)
            self._last_point = None
            self._stroke_start = None
            self._stroke_base = None
            self._straight_bounds = QRectF()
            self._show_hint()
            return True
        if self._item is None or self._scene is None:
            return False
        self._scene.removeItem(self._item)
        created_item = self._item
        self._item = None
        rect = created_item.rect
        if rect.width() * rect.height() >= MIN_AREA:
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, created_item, layer.layer_id)
                self._scene.command_stack.push(cmd)  # decision 2: no selection, no switch
        self._show_hint()
        return True

    def cancel(self) -> None:
        """End a live drag or brush stroke. A painted region survives, since only Enter,
        Escape, and a tool switch decide its fate (2.3)."""
        if self._paint_mask is not None:
            self._last_point = None
            self._stroke_start = None
            self._stroke_base = None
            self._straight_bounds = QRectF()
            return
        if self._item is not None and self._scene is not None and self._item.scene() is not None:
            self._scene.removeItem(self._item)
        self._item = None
