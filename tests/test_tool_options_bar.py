"""The Tool Options Bar's shared control set and per-tool contents (General UI PRD Section 5)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFontComboBox,
    QSpinBox,
    QToolButton,
    QWidget,
)

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import ApplyTarget, BubbleShape, TailStyle
from snapmock.core.document import Document
from snapmock.core.scene import SnapScene
from snapmock.items.callout_item import CalloutItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.callout_tool import CalloutTool
from snapmock.tools.eyedropper_tool import EyedropperTool
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.numbered_step_tool import NumberedStepTool
from snapmock.ui.color_picker import ColorPicker
from snapmock.ui.tool_options_bar import TOOL_OPTIONS_BAR_HEIGHT, ToolOptionsBar


def _bar(window: MainWindow) -> ToolOptionsBar:
    return window._tool_options  # noqa: SLF001


def _add_rects(window: MainWindow, count: int) -> list[RectangleItem]:
    scene = window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    items = []
    for i in range(count):
        item = RectangleItem(rect=QRectF(0, 0, 20, 10))
        item.setPos(i * 40, i * 5)
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        items.append(item)
    return items


def test_bar_height_and_object_name(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    assert bar.height() == TOOL_OPTIONS_BAR_HEIGHT
    assert bar.objectName() == "ToolOptionsBar"
    assert main_window.toolBarArea(bar) == Qt.ToolBarArea.TopToolBarArea


def test_shape_tools_compose_the_shared_set_in_order(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("rectangle")
    keys = list(bar.shared_widgets)
    # Basic Shape PRD 2.6's order (Vector Item Properties Phase 1 step 4)
    assert keys == [
        "stroke_color",
        "fill_color",
        "stroke_width",
        "stroke_style",
        "fill_opacity",
        "stroke_opacity",
        "shadow_enabled",
        "corner_radius",  # Basic Shape PRD 5.4 (Vector Item Properties Phase 3)
    ]
    assert isinstance(bar.shared_widgets["stroke_color"], ColorPicker)
    width = bar.shared_widgets["stroke_width"]
    assert isinstance(width, QDoubleSpinBox)
    assert (width.minimum(), width.maximum(), width.singleStep()) == (0.5, 50.0, 0.5)
    main_window.tool_manager.activate("line")
    assert list(bar.shared_widgets) == [
        "stroke_color",
        "stroke_width",
        "stroke_style",
        "stroke_opacity",
        "shadow_enabled",
    ]
    main_window.tool_manager.activate("freehand")
    assert list(bar.shared_widgets)[-1] == "smoothing"


def test_bar_edits_write_the_tool_defaults(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("rectangle")
    tool = main_window.tool_manager.tool("rectangle")
    assert tool is not None
    width = bar.shared_widgets["stroke_width"]
    assert isinstance(width, QDoubleSpinBox)
    width.setValue(7.5)
    assert tool.creation_defaults["stroke_width"] == 7.5
    swatch = bar.shared_widgets["fill_color"]
    assert isinstance(swatch, ColorPicker)
    swatch.color_changed.emit(QColor("#123456"))
    assert tool.creation_defaults["fill_color"] == QColor("#123456")
    opacity = bar.shared_widgets["fill_opacity"]
    assert isinstance(opacity, QSpinBox)
    opacity.setValue(40)
    assert tool.creation_defaults["fill_opacity"] == pytest.approx(0.4)
    assert "opacity_pct" not in tool.creation_defaults


def test_bar_and_property_panel_stay_in_step(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    panel = main_window._property_panel  # noqa: SLF001
    main_window.tool_manager.activate("rectangle")
    main_window.selection_manager.deselect_all()
    # Bar -> panel
    swatch = bar.shared_widgets["stroke_color"]
    assert isinstance(swatch, ColorPicker)
    swatch.color_changed.emit(QColor("#00FF00"))
    assert panel._stroke_color_picker.color == QColor("#00FF00")  # noqa: SLF001
    # Panel -> bar
    panel._on_stroke_w_spin_changed(9.0)  # noqa: SLF001
    width = bar.shared_widgets["stroke_width"]
    assert isinstance(width, QDoubleSpinBox)
    assert width.value() == 9.0
    panel._on_fill_color_changed(QColor("#0000FF"))  # noqa: SLF001
    fill = bar.shared_widgets["fill_color"]
    assert isinstance(fill, ColorPicker)
    assert fill.color == QColor("#0000FF")


def test_preferences_push_refreshes_the_bar(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("ellipse")
    main_window._settings.set_default_stroke_width(12.0)  # noqa: SLF001
    main_window._apply_tool_defaults()  # noqa: SLF001
    width = bar.shared_widgets["stroke_width"]
    assert isinstance(width, QDoubleSpinBox)
    assert width.value() == 12.0


def test_text_tool_controls_and_alignment_slot(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("text")
    keys = list(bar.shared_widgets)
    assert keys == [
        "font_family",
        "font_size",
        "bold",
        "italic",
        "underline",
        "text_color",
        "bg_color",
        "border_color",
        "border_width",
        "border_style",  # Text PRD 3.5 (Vector Item Properties Phase 1 step 4)
    ]
    assert isinstance(bar.shared_widgets["font_family"], QFontComboBox)
    size = bar.shared_widgets["font_size"]
    assert isinstance(size, QSpinBox)
    assert (size.minimum(), size.maximum()) == (6, 200)
    bold = bar.shared_widgets["bold"]
    assert isinstance(bold, QToolButton)
    tool = main_window.tool_manager.tool("text")
    assert tool is not None
    bold.setChecked(True)
    assert tool.creation_defaults["bold"] is True
    size.setValue(24)
    assert tool.creation_defaults["font_size"] == 24
    # The tool's own alignment buttons sit between the text colour and the box controls.
    texts = []
    for widget in bar.controls:
        if isinstance(widget, QToolButton) and widget.text() in ("L", "C", "R", "J"):
            texts.append(widget.text())
            if widget.text() == "C":
                widget.click()
    assert texts == ["L", "C", "R", "J"]
    assert tool.creation_defaults["horizontal_align"] == Qt.AlignmentFlag.AlignCenter


def test_callout_own_controls_write_defaults_applied_to_new_items(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("callout")
    tool = main_window.tool_manager.tool("callout")
    assert isinstance(tool, CalloutTool)
    tool._opt_shape.setCurrentIndex(tool._opt_shape.findData(BubbleShape.ELLIPSE))  # noqa: SLF001
    tool._opt_tail_w.setValue(33.0)  # noqa: SLF001
    for widget in bar.controls:
        if isinstance(widget, QToolButton) and widget.text() == "Curved":
            widget.click()
    assert tool.creation_defaults["bubble_shape"] == BubbleShape.ELLIPSE
    assert tool.creation_defaults["tail_style"] == TailStyle.CURVED
    assert tool.creation_defaults["tail_width"] == 33.0
    item = CalloutItem(text="", rect=QRectF(0, 0, 100, 50), tail_tip=QPointF(0, 100))
    tool._apply_creation_defaults(item)  # noqa: SLF001
    assert item.bubble_shape == BubbleShape.ELLIPSE
    assert item.tail_style == TailStyle.CURVED
    assert item.tail_width == 33.0


def test_select_tool_bar_shows_selection_and_alignment(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("select")
    label = bar._selection_label  # noqa: SLF001
    assert label is not None and label.text() == "No selection"
    copies = bar.selection_action_copies
    assert len(copies) == 8
    assert not any(a.isVisible() for a in copies)
    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items([items[0]])
    # The selection's bounding box, stroke included, as the transform handles show it.
    assert label.text() == "Selection: 1 item   W: 22 H: 12"
    assert not any(a.isVisible() for a in copies)
    main_window.selection_manager.select_items(items)
    assert label.text() == "Selection: 2 items   W: 62 H: 17"
    assert all(a.isVisible() for a in copies)
    copies[0].trigger()  # Align Left
    assert items[0].pos().x() == items[1].pos().x()


def test_select_tool_bar_follows_the_active_tab(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items(items)
    label = bar._selection_label  # noqa: SLF001
    assert label is not None and label.text().startswith("Selection: 2 items")
    second = Document(SnapScene(), parent=main_window)
    main_window._add_document(second)  # noqa: SLF001
    # A tab switch re-activates the tool, which rebuilds the bar and its label.
    label = bar._selection_label  # noqa: SLF001
    assert label is not None and label.text() == "No selection"
    main_window.documents.set_active_index(0)
    label = bar._selection_label  # noqa: SLF001
    assert label is not None and label.text().startswith("Selection: 2 items")


def test_eyedropper_bar_is_the_row_of_blur_prd_4_5(main_window: MainWindow) -> None:
    """Decision 3, option A: 4.5's controls in full, and no Apply buttons (5.3 corrected)."""
    from PyQt6.QtWidgets import QComboBox, QPushButton

    bar = _bar(main_window)
    tm = main_window.tool_manager
    tm.activate("eyedropper")
    tool = tm.tool("eyedropper")
    assert isinstance(tool, EyedropperTool)
    assert bar.eyedropper_value_text == "transparent"  # nothing sampled yet
    assert sorted(bar.eyedropper_size_buttons) == [1, 3, 5, 11]
    assert len(bar.eyedropper_history_swatches) == 8  # noqa: PLR2004
    assert not any(a.isVisible() for a in bar._eyedropper_history_actions)  # noqa: SLF001
    names = {w.accessibleName() for w in bar.findChildren(QWidget) if w.accessibleName()}
    assert {
        "Sampled color",
        "Color value",
        "Color format",
        "Apply target",
        "Copy to clipboard",
        "1x1 sample",
        "11x11 sample",
        "Color history 1",
    } <= names
    assert [c for c in bar.findChildren(QComboBox) if c.accessibleName() == "Apply target"]
    # The Apply to Stroke and Apply to Fill buttons are gone.
    assert not [b for b in bar.findChildren(QPushButton) if "Apply to" in b.text()]


def test_an_applied_sample_reaches_the_target_and_the_selection(
    main_window: MainWindow,
) -> None:
    bar = _bar(main_window)
    tm = main_window.tool_manager
    tm.activate("eyedropper")
    tool = tm.tool("eyedropper")
    assert isinstance(tool, EyedropperTool)
    # No selection: every tool with a stroke colour default takes the colour.
    bar._on_color_applied(QColor("#FF8800"))  # noqa: SLF001
    assert bar.eyedropper_value_text == "#FF8800"
    for tool_id in ("rectangle", "line", "freehand"):
        other = tm.tool(tool_id)
        assert other is not None
        assert other.creation_defaults["stroke_color"] == QColor("#FF8800")
    # With a selection, and the target changed: an undoable change to the items.
    items = _add_rects(main_window, 1)
    main_window.selection_manager.select_items([items[0]])
    tool.creation_defaults["apply_target"] = ApplyTarget.FILL_COLOR
    bar._on_color_applied(QColor("#FF8800"))  # noqa: SLF001
    assert items[0].fill_color == QColor("#FF8800")
    main_window.scene.command_stack.undo()
    assert items[0].fill_color != QColor("#FF8800")


def test_momentary_pick_sets_the_returned_tools_stroke_colour(main_window: MainWindow) -> None:
    tm = main_window.tool_manager
    tm.activate("rectangle")
    eyedropper = tm.tool("eyedropper")
    assert isinstance(eyedropper, EyedropperTool)
    main_window._momentary_pick_serial = eyedropper.pick_serial  # noqa: SLF001
    eyedropper._picked_color = QColor("#112233")  # noqa: SLF001
    eyedropper._pick_serial += 1  # noqa: SLF001
    main_window._apply_momentary_pick()  # noqa: SLF001
    rectangle = tm.tool("rectangle")
    assert rectangle is not None
    assert rectangle.creation_defaults["stroke_color"] == QColor("#112233")
    bar = _bar(main_window)
    swatch = bar.shared_widgets["stroke_color"]
    assert isinstance(swatch, ColorPicker)
    assert swatch.color == QColor("#112233")


def test_numbered_step_start_number_sets_the_next_number(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("numbered_step")
    tool = main_window.tool_manager.tool("numbered_step")
    assert isinstance(tool, NumberedStepTool)
    spin = bar.shared_widgets["start_number"]
    assert isinstance(spin, QSpinBox)
    assert (spin.minimum(), spin.maximum()) == (1, 999)
    spin.setValue(7)
    assert tool.creation_defaults["start_number"] == 7
    assert tool.next_number == 7


def test_freehand_smoothing_simplifies_the_path() -> None:
    # The two stages of Basic Shape PRD 9.3 (Basic Shape remainder decision 2): more
    # smoothing, fewer segments, the same ends, and the raw points untouched
    assert FreehandTool().creation_defaults["smoothing"] == 50
    raw = FreehandItem()
    for i in range(0, 200):
        raw.add_point(QPointF(i, (i % 2) * 2.0))
    many = raw.fit_segments(0.0)
    few = raw.fit_segments(1.0)
    assert len(few) < len(many)
    assert few[0][0] == raw.path_points[0]
    assert few[-1][3] == raw.path_points[-1]
    assert len(raw.path_points) == 200


def test_crop_checkbox_is_named_rule_of_thirds(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    main_window.tool_manager.activate("crop")
    boxes = [w.text() for w in bar.controls if isinstance(w, QCheckBox)]
    assert boxes == ["Rule of Thirds"]


def test_tools_without_options_show_only_their_name(main_window: MainWindow) -> None:
    bar = _bar(main_window)
    # The Blur tool gained its bar with the Basic Shape remainder work (Blur PRD 2.6)
    for tool_id in ("pan", "zoom"):
        main_window.tool_manager.activate(tool_id)
        assert bar.shared_widgets == {}
        # One control, the tool's name label; the strip and the overflow button are the
        # bar's own furniture and are not the tool's controls.
        assert len(bar.controls) == 1
