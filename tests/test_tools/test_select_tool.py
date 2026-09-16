"""Tests for SelectTool."""

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.group_commands import GroupItemsCommand
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.group_item import GroupItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.text_item import TextItem
from snapmock.tools.select_tool import SelectTool, _State
from snapmock.ui.transform_handles import ROTATE_HANDLE_OFFSET, HandlePosition


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def test_select_tool_identity() -> None:
    tool = SelectTool()
    assert tool.tool_id == "select"
    assert tool.display_name == "Select"


def test_select_tool_activation(scene: SnapScene) -> None:
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    assert tool._scene is scene
    tool.deactivate()
    assert tool._scene is None


def test_select_tool_creates_no_items(scene: SnapScene) -> None:
    """Select tool should not create items — only select existing ones."""
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem()
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    assert len(layer.item_ids) == 1


def _add_text_item(scene: SnapScene, text: str = "Hello") -> TextItem:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = TextItem()
    item.text = text
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def _begin_handle_drag(tool: SelectTool, item: TextItem) -> None:
    """Put the tool into HANDLE_DRAG state the way mouse_press does."""
    tool._state = _State.HANDLE_DRAG
    tool._handle_pos = HandlePosition.BOTTOM_CENTER
    tool._handle_item_originals = [(item, QPointF(item.pos()), QTransform(item.transform()))]
    tool._text_originals = {
        id(item): {
            "width": item._width,
            "height": item._height,
            "frame_height": item._frame_height(),
            "auto_size": item._auto_size,
            "font_size": item.text_document.defaultFont().pointSize(),
        }
    }


def test_vertical_resize_sets_explicit_height_and_disables_auto_size(scene: SnapScene) -> None:
    """Dragging a vertical handle locks the box height and turns auto-size off."""
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    item = _add_text_item(scene)
    sm.select_items([item])
    assert item.auto_size is True
    orig_frame_h = item._frame_height()

    _begin_handle_drag(tool, item)
    tool._apply_text_resize(item, 1.0, 2.0, QTransform(item.transform()))
    tool._handle_transform_release()

    assert item.auto_size is False
    assert item.text_height == pytest.approx(orig_frame_h * 2.0)
    assert item._frame_height() == pytest.approx(orig_frame_h * 2.0)

    # The resize is one undoable step that restores auto-size.
    scene.command_stack.undo()
    assert item.auto_size is True
    assert item.text_height is None
    assert item._frame_height() == pytest.approx(orig_frame_h)

    scene.command_stack.redo()
    assert item.auto_size is False
    assert item.text_height == pytest.approx(orig_frame_h * 2.0)


def test_horizontal_resize_keeps_auto_size(scene: SnapScene) -> None:
    """A width-only reflow does not lock the height."""
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    item = _add_text_item(scene)
    sm.select_items([item])
    orig_w = item.text_width

    _begin_handle_drag(tool, item)
    tool._apply_text_resize(item, 1.5, 1.0, QTransform(item.transform()))
    tool._handle_transform_release()

    assert item.auto_size is True
    assert item.text_height is None
    assert item.text_width == pytest.approx(orig_w * 1.5)


# --- groups (General UI PRD 3.6, Group and Ungroup kickoff step 4) ---


def _view_for(qtbot: QtBot, scene: SnapScene) -> SnapView:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(200, 200)
    return view


def _mouse(
    view: SnapView,
    kind: QEvent.Type,
    scene_pos: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    vp_pos = QPointF(view.mapFromScene(scene_pos))
    return QMouseEvent(kind, vp_pos, vp_pos, button, button, modifiers)


def _grouped_scene(
    scene: SnapScene,
) -> tuple[GroupItem, RectangleItem, RectangleItem, RectangleItem]:
    """A group of two rectangles (a at 0,0 and b at 200,0) and a loose rectangle c at 0,200."""
    layer = scene.layer_manager.active_layer
    assert layer is not None
    items = []
    for x, y in ((0, 0), (200, 0), (0, 200)):
        item = RectangleItem(rect=QRectF(0, 0, 100, 60))
        item.fill_color = item.stroke_color
        item.setPos(x, y)
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        items.append(item)
    a, b, c = items
    command = GroupItemsCommand(scene, [a, b])
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    return group, a, b, c


def test_click_on_a_member_selects_its_group_and_frames_it(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(250, 30)))  # inside b
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(250, 30)))
    assert sm.items == [group]
    assert tool._handles is not None
    assert tool._handles.current_rect == group.sceneBoundingRect()
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(50, 230)))  # inside c
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(50, 230)))
    assert sm.items == [c]


def test_rubber_band_over_members_selects_the_group_once(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(-20, -20)))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(320, 80)))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(320, 80)))
    assert sm.items == [group]


def test_drag_on_a_member_moves_the_whole_group(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    before = (a.sceneBoundingRect(), b.sceneBoundingRect(), c.sceneBoundingRect())
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(50, 30)))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(80, 70)))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(80, 70)))
    assert a.sceneBoundingRect() == before[0].translated(30, 40)
    assert b.sceneBoundingRect() == before[1].translated(30, 40)
    assert c.sceneBoundingRect() == before[2]
    assert scene.command_stack.undo_text.endswith("Move 1 item")


def test_arrow_keys_nudge_the_group_as_one_item(qtbot: QtBot, scene: SnapScene) -> None:
    _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    sm.select_items([group])
    before = a.sceneBoundingRect()
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert tool.key_press(event)
    assert a.sceneBoundingRect() == before.translated(10, 0)
    assert group.pos().x() == pytest.approx(-1 + 10)


def test_tab_cycles_a_group_as_one_stop(qtbot: QtBot, scene: SnapScene) -> None:
    _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    sm.deselect_all()
    seen = []
    for _ in range(3):
        assert tool.cycle_selection(forward=True)
        seen.append(sm.items[0])
    assert seen == [group, c, group]  # the group holds b's place below c


def test_double_click_on_a_group_selects_it_and_says_to_ungroup(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    text = TextItem()
    text.text = "Hello"
    text.setPos(0, 0)
    scene.command_stack.push(AddItemCommand(scene, text, layer.layer_id))
    other = RectangleItem(rect=QRectF(0, 0, 100, 60))
    other.setPos(200, 0)
    scene.command_stack.push(AddItemCommand(scene, other, layer.layer_id))
    command = GroupItemsCommand(scene, [text, other])
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    assert tool.mouse_double_click(_mouse(view, QEvent.Type.MouseButtonDblClick, QPointF(10, 8)))
    assert sm.items == [group]
    assert "Ungroup" in tool.status_hint
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(-50, -50)))
    assert "Ungroup" not in tool.status_hint


def test_text_tool_does_not_edit_a_member(qtbot: QtBot, scene: SnapScene) -> None:
    from snapmock.tools.text_tool import TextTool

    _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    text = TextItem()
    text.text = "Hello"
    text.setPos(0, 0)
    scene.command_stack.push(AddItemCommand(scene, text, layer.layer_id))
    other = RectangleItem(rect=QRectF(0, 0, 100, 60))
    other.setPos(200, 0)
    scene.command_stack.push(AddItemCommand(scene, other, layer.layer_id))
    text_tool = TextTool()
    text_tool.activate(scene, sm)
    assert text_tool._text_item_at(QPointF(10, 8)) is text
    scene.command_stack.push(GroupItemsCommand(scene, [text, other]))
    assert text_tool._text_item_at(QPointF(10, 8)) is None


def test_delete_removes_the_group_with_its_members(qtbot: QtBot, scene: SnapScene) -> None:
    _view_for(qtbot, scene)
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    group, a, b, c = _grouped_scene(scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    sm.select_items([group])
    delete = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    assert tool.key_press(delete)
    assert scene.annotation_items() == [c]
    assert scene.all_annotation_items() == [c]
    assert layer.item_ids == [c.item_id]
    scene.command_stack.undo()
    assert set(scene.annotation_items()) == {group, c}
    assert a.parentItem() is group
    assert layer.item_ids == [c.item_id, group.item_id]


# ---- the ΔX / ΔY readout while dragging (end-to-end pass finding 3) ----


def _filled_rectangle(scene: SnapScene) -> RectangleItem:
    """A 200 by 120 rectangle at (100, 100) whose interior takes a press."""
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 200, 120))
    item.fill_color = item.stroke_color
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def test_drag_readout_is_the_overlay_not_a_tooltip(qtbot: QtBot, scene: SnapScene) -> None:
    """The move readout is the widget over the viewport the drawing tools use, never a Qt
    tooltip window, which on Linux takes the view's focus on every move and made a drag
    jump (Technical Architecture PRD 3.4; end-to-end pass finding 3)."""
    from PyQt6.QtWidgets import QToolTip

    from snapmock.ui.dimension_overlay import existing_dimension_overlay

    view = _view_for(qtbot, scene)
    item = _filled_rectangle(scene)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    viewport = view.viewport()
    assert viewport is not None

    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 150)))
    assert tool._state is _State.DRAGGING
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(170, 180)))
    assert item.pos() == QPointF(120, 130)
    overlay = existing_dimension_overlay(viewport)
    assert overlay is not None and not overlay.isHidden()
    assert overlay.text == "ΔX: +20  ΔY: +30"
    assert not overlay.constrained
    assert not QToolTip.isVisible()
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(170, 180)))
    assert overlay.isHidden()
    assert item.pos() == QPointF(120, 130)


def test_resize_and_rotate_readouts_are_the_overlay_too(qtbot: QtBot, scene: SnapScene) -> None:
    from PyQt6.QtWidgets import QToolTip

    from snapmock.ui.dimension_overlay import existing_dimension_overlay

    view = _view_for(qtbot, scene)
    _filled_rectangle(scene)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    viewport = view.viewport()
    assert viewport is not None
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 150)))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(150, 150)))
    assert tool._handles is not None
    for corner, expected in ((True, " × "), (False, "°")):
        frame = tool._handles.current_rect
        handle_pos = (
            frame.bottomRight()
            if corner
            else QPointF(frame.center().x(), frame.top() - ROTATE_HANDLE_OFFSET)
        )
        tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, handle_pos))
        assert tool._state is _State.HANDLE_DRAG
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, handle_pos + QPointF(30, 20)))
        overlay = existing_dimension_overlay(viewport)
        assert overlay is not None and not overlay.isHidden()
        assert expected in overlay.text, overlay.text
        assert not QToolTip.isVisible()
        tool.mouse_release(
            _mouse(view, QEvent.Type.MouseButtonRelease, handle_pos + QPointF(30, 20))
        )
        assert overlay.isHidden()


def test_cancel_during_a_drag_takes_the_readout(qtbot: QtBot, scene: SnapScene) -> None:
    from snapmock.ui.dimension_overlay import existing_dimension_overlay

    view = _view_for(qtbot, scene)
    _filled_rectangle(scene)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    viewport = view.viewport()
    assert viewport is not None

    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 150)))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(190, 150)))
    overlay = existing_dimension_overlay(viewport)
    assert overlay is not None and not overlay.isHidden()
    tool.cancel()
    assert overlay.isHidden()


# ---- Snap to Grid over a slow drag (end-to-end pass finding 3, the cause) ----


def test_a_slow_drag_with_snap_to_grid_on_still_moves_the_item(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """With Snap to Grid on, the item lands on grid multiples of the whole movement since
    the press, so a pointer that moves 3 px per event still carries the item along.
    Before the fix each event's own increment was rounded to the grid and the remainder
    thrown away, so slow movement moved nothing and only a flick moved a grid step."""
    view = _view_for(qtbot, scene)
    item = _filled_rectangle(scene)
    view.set_grid_size(20)
    view.set_snap_to_grid(True)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    # the handles' frame sits half a stroke outside the rectangle's own line; the line is
    # what snaps (decision 5 as Doug corrected it)
    assert item.sceneBoundingRect().topLeft() != item.scene_geometry_rect().topLeft()
    assert item.scene_geometry_rect().topLeft() == QPointF(100, 100)
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 150)))
    seen: list[float] = []
    for i in range(1, 40):
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(150 + 2 * i, 150 + 3 * i)))
        seen.append(item.pos().y())
    # 78 px right and 117 px down since the press: the rectangle's own corner lands on
    # the grid line nearest where the pointer carried it (decision 5, option B)
    assert item.pos() == QPointF(180, 220)
    # and the item moved during the drag in grid steps, not only at the end
    assert sorted(set(seen)) == [100, 120, 140, 160, 180, 200, 220]
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(228, 267)))
    assert item.pos() == QPointF(180, 220)
    assert scene.command_stack.undo_text.endswith("Move 1 item")


def test_snap_to_grid_puts_an_off_grid_item_onto_the_grid(qtbot: QtBot, scene: SnapScene) -> None:
    """Decision 5, option B: a selection that starts 7 px off the grid lands on it after
    a move, as guides work, rather than staying 7 px off (the 3.3 rule as first built)."""
    view = _view_for(qtbot, scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 200, 120))
    item.fill_color = item.stroke_color
    item.setPos(107, 133)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    view.set_grid_size(20)
    view.set_snap_to_grid(True)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 180)))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(163, 191)))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(163, 191)))
    # the rectangle's corner was at (107, 133), carried to (120, 144): nearest grid (120, 140)
    assert item.pos() == QPointF(120, 140)


def test_shift_arrow_snaps_to_the_next_grid_line_then_steps(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """Finding 4 as Doug corrected it: Shift+Arrow takes the items' own top-left corner to
    the next grid line in the arrow's direction, one pixel if that is the distance, and a
    whole step once the corner is on a line; Arrow alone stays one pixel."""
    view = _view_for(qtbot, scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 200, 120))
    item.setPos(107, 133)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    view.set_grid_size(20)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    tool._selection_manager.select(item)  # noqa: SLF001

    def press(key: Qt.Key, shift: bool = True) -> None:
        mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        assert tool.key_press(QKeyEvent(QEvent.Type.KeyPress, key, mods))

    press(Qt.Key.Key_Right)
    assert item.pos() == QPointF(120, 133)  # 13 px, to the line
    press(Qt.Key.Key_Right)
    assert item.pos() == QPointF(140, 133)  # a whole step, from the line
    press(Qt.Key.Key_Left)
    assert item.pos() == QPointF(120, 133)
    press(Qt.Key.Key_Down)
    assert item.pos() == QPointF(120, 140)  # 7 px
    press(Qt.Key.Key_Up)
    assert item.pos() == QPointF(120, 120)
    press(Qt.Key.Key_Up)
    assert item.pos() == QPointF(120, 100)
    press(Qt.Key.Key_Right, shift=False)
    assert item.pos() == QPointF(121, 100)  # Arrow alone: one pixel
    press(Qt.Key.Key_Left)
    assert item.pos() == QPointF(120, 100)  # back to the line, 1 px
    # snapping works whether or not View > Snap to Grid is on: Shift asks for the grid
    assert not view.snap_to_grid


def test_geometry_rect_is_the_shape_without_its_padding(qtbot: QtBot, scene: SnapScene) -> None:
    from snapmock.items.group_item import GroupItem

    layer = scene.layer_manager.active_layer
    assert layer is not None
    a = RectangleItem(QRectF(0, 0, 50, 30))
    a.stroke_width = 6
    a.setPos(10, 10)
    b = RectangleItem(QRectF(0, 0, 20, 20))
    b.setPos(100, 100)
    for it in (a, b):
        scene.command_stack.push(AddItemCommand(scene, it, layer.layer_id))
    assert a.geometry_rect() == QRectF(0, 0, 50, 30)
    assert a.boundingRect().left() < 0 and a.boundingRect().width() > 50
    assert a.scene_geometry_rect() == QRectF(10, 10, 50, 30)
    command = GroupItemsCommand(scene, [a, b])
    scene.command_stack.push(command)
    group = command.group
    assert isinstance(group, GroupItem)
    assert group.scene_geometry_rect() == QRectF(10, 10, 110, 110)


def test_a_slow_drag_without_snap_follows_the_pointer_exactly(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view_for(qtbot, scene)
    item = _filled_rectangle(scene)
    tool = SelectTool()
    tool.activate(scene, SelectionManager(scene))
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(150, 150)))
    for i in range(1, 40):
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(150 + 2 * i, 150 + 3 * i)))
    assert item.pos() == QPointF(178, 217)
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(228, 267)))
    assert item.pos() == QPointF(178, 217)
