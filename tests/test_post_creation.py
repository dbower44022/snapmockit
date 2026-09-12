"""The post-creation rule (Basic Shape PRD 2.1's last mouse-release step, 2.5).

Decision 2 of the shape tools' shared drawing work, option A: every tool that draws — the
seven shape tools, the Blur tool, and the Highlighter — stays active after a shape is made
and leaves the new item unselected, so shapes can be drawn in quick succession, each its
own undo step. The Text and Callout tools are excepted: their PRD puts a new item straight
into inline edit mode. The switch reached the tool manager through the view's window, so
these tests draw through the ``main_window`` fixture, where a switch would be seen.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from snapmock.config.constants import BlurRegionShape, PolygonMode
from snapmock.core.view import SnapView
from snapmock.items.blur_item import BlurItem
from snapmock.main_window import MainWindow
from snapmock.tools.base_tool import BaseTool

NONE = Qt.KeyboardModifier.NoModifier
LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton


def _mouse(
    view: SnapView, kind: QEvent.Type, pos: QPointF, buttons: Qt.MouseButton = LEFT
) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, LEFT, buttons, NONE)


def _press(tool: BaseTool, view: SnapView, pos: QPointF) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos))


def _move(tool: BaseTool, view: SnapView, pos: QPointF, buttons: Qt.MouseButton = LEFT) -> None:
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, pos, buttons))


def _release(tool: BaseTool, view: SnapView, pos: QPointF) -> None:
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, pos))


def _drag(tool: BaseTool, view: SnapView, start: QPointF, end: QPointF) -> None:
    _press(tool, view, start)
    _move(tool, view, QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2))
    _move(tool, view, end)
    _release(tool, view, end)


def _arc(tool: BaseTool, view: SnapView, start: QPointF, end: QPointF) -> None:
    _drag(tool, view, start, end)
    peak = QPointF((start.x() + end.x()) / 2, start.y() - 30)
    _move(tool, view, peak, NO_BUTTON)
    _press(tool, view, peak)  # the click that confirms the curvature (7.2)
    _release(tool, view, peak)


def _polygon(tool: BaseTool, view: SnapView, start: QPointF, _end: QPointF) -> None:
    for dx, dy in ((0, 0), (60, 0), (30, 40)):
        pos = QPointF(start.x() + dx, start.y() + dy)
        _press(tool, view, pos)
        _release(tool, view, pos)
    tool.key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, NONE))


SHAPE_TOOLS = ("rectangle", "ellipse", "line", "arrow", "freehand", "arc", "polygon")


def _draw(tool_id: str, tool: BaseTool, view: SnapView, start: QPointF, end: QPointF) -> None:
    if tool_id == "arc":
        _arc(tool, view, start, end)
    elif tool_id == "polygon":
        _polygon(tool, view, start, end)
    else:
        _drag(tool, view, start, end)


def _active(main_window: MainWindow, tool_id: str) -> BaseTool:
    main_window.tool_manager.activate(tool_id)
    tool = main_window.tool_manager.active_tool
    assert tool is not None and tool.tool_id == tool_id
    return tool


# --------------------------------------------------------------- the seven shape tools


@pytest.mark.parametrize("tool_id", SHAPE_TOOLS)
def test_three_shapes_in_succession_with_nothing_between(
    main_window: MainWindow, tool_id: str
) -> None:
    """2.5's rapid drawing: no intermediate step, and each shape its own undo step."""
    scene, view = main_window.scene, main_window.view
    tool = _active(main_window, tool_id)

    for row in range(3):
        _draw(tool_id, tool, view, QPointF(60, 60 + row * 80), QPointF(160, 110 + row * 80))
        assert main_window.tool_manager.active_tool is tool
        assert main_window.selection_manager.items == []

    assert len(scene.annotation_items()) == 3  # noqa: PLR2004
    assert scene.command_stack.count == 3  # noqa: PLR2004
    for remaining in (2, 1, 0):
        scene.command_stack.undo()
        assert len(scene.annotation_items()) == remaining


@pytest.mark.parametrize("tool_id", SHAPE_TOOLS)
def test_the_new_shape_is_there_to_select_with_the_select_tool(
    main_window: MainWindow, tool_id: str
) -> None:
    """2.5: to edit the shape the user switches to the Select tool (V) and selects it."""
    view = main_window.view
    tool = _active(main_window, tool_id)
    _draw(tool_id, tool, view, QPointF(60, 60), QPointF(160, 110))
    (item,) = main_window.scene.annotation_items()
    assert not item.isSelected()

    main_window.tool_manager.activate("select")
    main_window.selection_manager.select(item)
    assert main_window.selection_manager.items == [item]


def test_the_polygon_stays_active_in_regular_mode(main_window: MainWindow) -> None:
    view = main_window.view
    tool = _active(main_window, "polygon")
    tool.creation_defaults["polygon_mode"] = PolygonMode.REGULAR
    for x in (100, 250):
        _drag(tool, view, QPointF(x, 150), QPointF(x + 50, 150))
    assert main_window.tool_manager.active_tool_id == "polygon"
    assert len(main_window.scene.annotation_items()) == 2  # noqa: PLR2004
    assert main_window.selection_manager.items == []


def test_the_hint_returns_to_idle_after_each_shape(main_window: MainWindow) -> None:
    """The hint tables return to the Idle row when a shape is made: the tool is ready."""
    view = main_window.view
    label = main_window._status_bar._hint_label  # noqa: SLF001
    for tool_id in ("rectangle", "arc", "polygon"):
        tool = _active(main_window, tool_id)
        idle = tool.status_hint
        _draw(tool_id, tool, view, QPointF(60, 60), QPointF(160, 110))
        assert label.text() == idle


# --------------------------------------------------------------- the Blur tool and the Highlighter


@pytest.mark.parametrize(
    "shape", [BlurRegionShape.RECTANGLE, BlurRegionShape.ELLIPSE, BlurRegionShape.FREEFORM]
)
def test_the_blur_tool_stays_active_after_a_region(
    main_window: MainWindow, shape: BlurRegionShape
) -> None:
    """Decision 2 reaches the Blur tool's drag-drawn and brush-painted release paths."""
    view = main_window.view
    tool = _active(main_window, "blur")
    tool.creation_defaults["region_shape"] = shape
    for row in range(2):
        _drag(tool, view, QPointF(60, 60 + row * 100), QPointF(200, 120 + row * 100))
        if shape is BlurRegionShape.FREEFORM:
            tool.key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, NONE))
        assert main_window.tool_manager.active_tool_id == "blur"
        assert main_window.selection_manager.items == []
    regions = [i for i in main_window.scene.annotation_items() if isinstance(i, BlurItem)]
    assert len(regions) == 2  # noqa: PLR2004


def test_the_blur_tool_stays_active_after_a_whole_layer_region(main_window: MainWindow) -> None:
    view = main_window.view
    tool = _active(main_window, "blur")
    tool.creation_defaults["region_shape"] = BlurRegionShape.WHOLE_LAYER
    _press(tool, view, QPointF(100, 100))
    _release(tool, view, QPointF(100, 100))
    assert main_window.tool_manager.active_tool_id == "blur"
    assert main_window.selection_manager.items == []
    assert len(main_window.scene.annotation_items()) == 1


def test_a_painted_region_finished_by_a_tool_switch_is_not_selected(
    main_window: MainWindow,
) -> None:
    view = main_window.view
    tool = _active(main_window, "blur")
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    _drag(tool, view, QPointF(60, 60), QPointF(200, 120))
    main_window.tool_manager.activate("rectangle")
    assert len(main_window.scene.annotation_items()) == 1
    assert main_window.selection_manager.items == []


def test_the_highlighter_stays_active_after_a_stroke(main_window: MainWindow) -> None:
    view = main_window.view
    tool = _active(main_window, "highlight")
    for row in range(3):
        _drag(tool, view, QPointF(60, 60 + row * 40), QPointF(260, 60 + row * 40))
        assert main_window.tool_manager.active_tool_id == "highlight"
        assert main_window.selection_manager.items == []
    assert main_window.scene.command_stack.count == 3  # noqa: PLR2004


# --------------------------------------------------------------- the Text and Callout tools


def test_the_text_tool_still_selects_its_new_item_for_editing(main_window: MainWindow) -> None:
    """Excepted by decision 2: the new text item goes straight into inline edit mode."""
    view = main_window.view
    tool = _active(main_window, "text")
    _press(tool, view, QPointF(100, 100))
    _release(tool, view, QPointF(100, 100))
    assert main_window.tool_manager.active_tool_id == "text"
    selected = main_window.selection_manager.items
    assert len(selected) == 1


def test_the_callout_tool_still_hands_its_new_item_to_the_text_tool(
    main_window: MainWindow,
) -> None:
    view = main_window.view
    tool = _active(main_window, "callout")
    _drag(tool, view, QPointF(100, 100), QPointF(260, 180))
    assert main_window.tool_manager.active_tool_id == "text"
    assert len(main_window.selection_manager.items) == 1
