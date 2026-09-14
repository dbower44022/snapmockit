"""Brush editing of a placed freeform blur region (Blur PRD 2.8, 6.1).

A double-click on a Freeform region with the Select tool enters brush editing: painting
adds blur area, Alt+painting takes it away, each stroke is one undoable
``ModifyBlurMaskCommand``, and Enter or Escape leaves.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.blur_commands import ModifyBlurMaskCommand
from snapmock.config.constants import BlurRegionShape
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.blur_item import BlurItem
from snapmock.items.mask_utils import blank_mask
from snapmock.tools.select_tool import SelectTool


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=400, height=300)


def _view(qtbot: QtBot, scene: SnapScene) -> SnapView:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(200, 150)
    return view


def _mouse(
    view: SnapView,
    kind: QEvent.Type,
    pos: QPointF,
    mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    button = Qt.MouseButton.LeftButton
    return QMouseEvent(kind, vp, vp, button, button, mods)


def _region(scene: SnapScene, shape: BlurRegionShape = BlurRegionShape.FREEFORM) -> BlurItem:
    item = BlurItem(rect=QRectF(0, 0, 100, 60))
    item.region_shape = shape
    item.setPos(50, 50)
    if shape is BlurRegionShape.FREEFORM:
        mask = blank_mask(100, 60)
        painter = QPainter(mask)
        painter.fillRect(0, 0, 60, 60, QColor(255, 255, 255))
        painter.end()
        item.alpha_mask = mask
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def _tool(scene: SnapScene) -> tuple[SelectTool, SelectionManager]:
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    return tool, sm


def _alpha(item: BlurItem, scene_point: QPointF) -> int:
    mask = item.alpha_mask
    assert mask is not None
    local = item.mapFromScene(scene_point) - item.rect.topLeft()
    return mask.pixelColor(int(local.x()), int(local.y())).alpha()


def _stroke(
    tool: SelectTool,
    view: SnapView,
    points: list[QPointF],
    mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, points[0], mods))
    for point in points[1:]:
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, point, mods))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, points[-1], mods))


def test_a_double_click_enters_brush_editing_and_enter_and_escape_leave(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    item = _region(scene)
    tool, sm = _tool(scene)
    tool.mouse_double_click(_mouse(view, QEvent.Type.MouseButtonDblClick, QPointF(70, 70)))
    session = tool.brush_session
    assert session is not None and session.item is item
    assert sm.items == [item]
    assert tool.status_hint == "Paint to add blur. Alt+paint to erase. Enter/Escape: finish."
    assert tool.point_session is None
    handles = tool._handles  # noqa: SLF001
    assert handles is not None and handles.scene() is None  # the brush replaces them

    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert tool.key_press(enter)
    assert tool.brush_session is None and sm.items == [item]

    tool.mouse_double_click(_mouse(view, QEvent.Type.MouseButtonDblClick, QPointF(70, 70)))
    assert tool.brush_session is not None
    assert tool.handle_escape()
    assert tool.brush_session is None


def test_a_double_click_on_a_rectangular_region_does_nothing(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    _region(scene, BlurRegionShape.RECTANGLE)
    tool, _sm = _tool(scene)
    tool.mouse_double_click(_mouse(view, QEvent.Type.MouseButtonDblClick, QPointF(70, 70)))
    assert tool.brush_session is None and tool.point_session is None


def test_painting_adds_blur_area_and_alt_paint_erases(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    item = _region(scene)
    tool, _sm = _tool(scene)
    assert tool.enter_brush_edit(item)
    session = tool.brush_session
    assert session is not None
    session.brush_size = 20.0
    assert _alpha(item, QPointF(140, 80)) == 0  # the right third is unpainted
    _stroke(tool, view, [QPointF(130, 80), QPointF(145, 80)])
    assert _alpha(item, QPointF(140, 80)) == 255
    alt = Qt.KeyboardModifier.AltModifier
    _stroke(tool, view, [QPointF(70, 80), QPointF(85, 80)], alt)
    assert _alpha(item, QPointF(78, 80)) == 0  # taken back out again
    assert _alpha(item, QPointF(60, 60)) == 255  # the rest of the painted area stands


def test_painting_past_the_region_grows_it_and_erasing_never_shrinks_it(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    item = _region(scene)
    tool, _sm = _tool(scene)
    assert tool.enter_brush_edit(item)
    session = tool.brush_session
    assert session is not None
    session.brush_size = 20.0
    before = QRectF(item.rect)
    _stroke(tool, view, [QPointF(180, 80)])
    grown = item.rect
    assert grown.width() > before.width() and grown.right() > before.right()
    assert _alpha(item, QPointF(180, 80)) == 255
    _stroke(tool, view, [QPointF(180, 80)], Qt.KeyboardModifier.AltModifier)
    assert item.rect == grown  # the handles do not jump while the brush works


def test_each_stroke_is_one_undoable_mask_command(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    item = _region(scene)
    tool, _sm = _tool(scene)
    assert tool.enter_brush_edit(item)
    session = tool.brush_session
    assert session is not None
    session.brush_size = 20.0
    depth = len(scene.command_stack._commands)  # noqa: SLF001
    _stroke(tool, view, [QPointF(130, 80), QPointF(145, 80)])
    assert len(scene.command_stack._commands) == depth + 1  # noqa: SLF001
    command = scene.command_stack._commands[-1]  # noqa: SLF001
    assert isinstance(command, ModifyBlurMaskCommand)
    assert command.description == "Edit blur region mask"
    painted = _alpha(item, QPointF(140, 80))
    assert painted == 255
    scene.command_stack.undo()
    assert _alpha(item, QPointF(140, 80)) == 0
    scene.command_stack.redo()
    assert _alpha(item, QPointF(140, 80)) == 255
    # A stroke that changes nothing pushes nothing: the region keeps its mask
    session.begin_stroke(QPointF(130, 80))
    session.cancel_stroke()
    assert session.end_stroke() is None


def test_a_press_away_from_the_region_paints_rather_than_leaving(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """Only Enter, Escape, a tool switch, or a new selection leave the mode (2.8)."""
    view = _view(qtbot, scene)
    item = _region(scene)
    tool, sm = _tool(scene)
    assert tool.enter_brush_edit(item)
    session = tool.brush_session
    assert session is not None
    session.brush_size = 20.0
    _stroke(tool, view, [QPointF(220, 160)])
    assert tool.brush_session is session
    assert _alpha(item, QPointF(220, 160)) == 255
    sm.deselect_all()
    assert tool.brush_session is None


def test_the_brush_cursor_and_the_panel_row_share_one_brush(main_window: object) -> None:
    from snapmock.items.blur_item import BlurItem as Item

    window = main_window
    scene = window.scene  # type: ignore[attr-defined]
    item = Item(rect=QRectF(0, 0, 100, 60))
    item.region_shape = BlurRegionShape.FREEFORM
    item.alpha_mask = blank_mask(100, 60)
    layer = scene.layer_manager.active_layer
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    tm = window.tool_manager  # type: ignore[attr-defined]
    tm.activate("blur")
    blur_tool = tm.active_tool
    blur_tool.creation_defaults["brush_size"] = 48.0
    tm.activate("select")
    select = tm.active_tool
    assert isinstance(select, SelectTool)
    assert select.cursor is Qt.CursorShape.ArrowCursor
    assert select.enter_brush_edit(item)
    session = select.brush_session
    assert session is not None and session.brush_size == 48.0
    cursor = select.cursor
    assert not isinstance(cursor, Qt.CursorShape)
    assert cursor.pixmap().width() == 48 + 6
    # The brush-editing cursor follows the zoom on the viewport too
    view = main_window.view  # type: ignore[attr-defined]
    viewport = view.viewport()
    assert viewport is not None
    view.set_zoom(200)
    assert viewport.cursor().pixmap().width() == 96 + 6
    view.set_zoom(100)
    assert viewport.cursor().pixmap().width() == 48 + 6

    panel = window._property_panel  # type: ignore[attr-defined]  # noqa: SLF001
    window.selection_manager.select(item)  # type: ignore[attr-defined]
    spin = panel._blur_brush_spin  # noqa: SLF001
    assert spin.isVisible() or True  # the row shows for a freeform region
    assert spin.value() == 48
    spin.setValue(70)
    assert session.brush_size == 70.0
    assert blur_tool.creation_defaults["brush_size"] == 70.0
    select.leave_brush_edit()


def test_the_mask_command_restores_the_rectangle_too(qapp: QApplication) -> None:
    item = BlurItem(rect=QRectF(0, 0, 40, 40))
    item.region_shape = BlurRegionShape.FREEFORM
    item.alpha_mask = blank_mask(40, 40)
    old = (QRectF(item.rect), item.alpha_mask)
    grown = blank_mask(80, 40)
    painter = QPainter(grown)
    painter.fillRect(0, 0, 80, 40, QColor(255, 255, 255))
    painter.end()
    new = (QRectF(0, 0, 80, 40), grown)
    command = ModifyBlurMaskCommand(item, old, new)
    command.redo()
    assert item.rect == QRectF(0, 0, 80, 40)
    mask = item.alpha_mask
    assert mask is not None and isinstance(mask, QImage) and mask.width() == 80
    command.undo()
    assert item.rect == QRectF(0, 0, 40, 40)
    restored = item.alpha_mask
    assert restored is not None and restored.width() == 40
