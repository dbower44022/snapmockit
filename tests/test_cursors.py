"""The canvas cursor table of General UI PRD 6.6."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.text_item import TextItem
from snapmock.main_window import MainWindow
from snapmock.tools.eyedropper_tool import EyedropperTool
from snapmock.tools.pan_tool import PanTool
from snapmock.tools.raster_select_tool import RasterSelectTool
from snapmock.tools.select_tool import SelectTool
from snapmock.tools.text_tool import TextTool
from snapmock.tools.tool_manager import ToolManager
from snapmock.tools.zoom_tool import ZoomTool
from snapmock.ui import cursors
from snapmock.ui.transform_handles import HandlePosition, TransformHandles

Shape = Qt.CursorShape


class TestCursorFactories:
    @pytest.fixture(autouse=True)
    def _fresh(self, qapp: QApplication) -> None:
        cursors.reset_cursor_cache()

    def test_glyph_cursors_are_pixmaps_with_hotspots(self) -> None:
        for factory, hot in (
            (cursors.rotate_cursor, QPoint(12, 12)),
            (cursors.zoom_in_cursor, QPoint(10, 10)),
            (cursors.zoom_out_cursor, QPoint(10, 10)),
            (cursors.eyedropper_cursor, QPoint(4, 20)),
            (cursors.raster_select_cursor, QPoint(12, 12)),
            (cursors.text_hover_cursor, QPoint(12, 12)),
        ):
            cursor = factory()
            assert cursor.shape() == Shape.BitmapCursor, factory.__name__
            assert cursor.hotSpot() == hot, factory.__name__
            pixmap = cursor.pixmap()
            assert pixmap.width() == cursors.CURSOR_SIZE
            image = pixmap.toImage()
            painted = any(
                image.pixelColor(x, y).alpha() > 0
                for x in range(image.width())
                for y in range(image.height())
            )
            assert painted, factory.__name__

    def test_cursors_are_cached_and_a_missing_glyph_falls_back(self) -> None:
        assert cursors.zoom_in_cursor() is cursors.zoom_in_cursor()
        assert cursors.glyph_cursor("no-such-glyph", 0, 0).shape() == Shape.CrossCursor


def _view_with_tools(qtbot: QtBot) -> tuple[SnapScene, SnapView, ToolManager]:
    scene = SnapScene(width=800, height=600)
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    sm = SelectionManager(scene)
    tm = ToolManager(scene, sm)
    for tool in (
        SelectTool(),
        TextTool(),
        ZoomTool(),
        EyedropperTool(),
        RasterSelectTool(),
        PanTool(),
    ):
        tm.register(tool)
    view.set_tool_manager(tm)
    return scene, view, tm


def _add_rect(scene: SnapScene) -> RectangleItem:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 100, 100))
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def _move(
    view: SnapView, scene_pos: QPointF, buttons: Qt.MouseButton = Qt.MouseButton.NoButton
) -> None:
    vp_pos = QPointF(view.mapFromScene(scene_pos))
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        vp_pos,
        vp_pos,
        Qt.MouseButton.NoButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(event)


def _press(view: SnapView, scene_pos: QPointF) -> None:
    vp_pos = QPointF(view.mapFromScene(scene_pos))
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        vp_pos,
        vp_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(event)


def _release(view: SnapView, scene_pos: QPointF) -> None:
    vp_pos = QPointF(view.mapFromScene(scene_pos))
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        vp_pos,
        vp_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(event)


def _shape(view: SnapView) -> Qt.CursorShape:
    vp = view.viewport()
    assert vp is not None
    return vp.cursor().shape()


def test_select_tool_hover_open_hand_drag_closed_hand_locked_forbidden(qtbot: QtBot) -> None:
    scene, view, tm = _view_with_tools(qtbot)
    _add_rect(scene)
    tm.activate("select")
    view.centerOn(150, 150)
    _move(view, QPointF(20, 20))
    assert _shape(view) == Shape.ArrowCursor
    on_stroke = QPointF(100, 150)  # a transparent fill is not a hit; the stroke is
    _move(view, on_stroke)
    assert _shape(view) == Shape.OpenHandCursor
    _press(view, on_stroke)
    assert _shape(view) == Shape.ClosedHandCursor
    _move(view, QPointF(110, 160), Qt.MouseButton.LeftButton)
    assert _shape(view) == Shape.ClosedHandCursor
    _release(view, QPointF(110, 160))
    assert _shape(view) == Shape.SizeHorCursor  # released over the middle-left handle
    _move(view, QPointF(135, 110))
    assert _shape(view) == Shape.OpenHandCursor  # the top stroke, clear of the handles
    # Selected: the whole selection rectangle drags, so its interior is an open hand too
    _move(view, QPointF(160, 160))
    assert _shape(view) == Shape.OpenHandCursor
    layer = scene.layer_manager.active_layer
    assert layer is not None
    tm._selection_manager.deselect_all()  # noqa: SLF001
    scene.layer_manager.set_locked(layer.layer_id, True)
    _move(view, QPointF(110, 160))
    assert _shape(view) == Shape.ForbiddenCursor
    _move(view, QPointF(20, 20))
    assert _shape(view) == Shape.ArrowCursor


def test_select_tool_hover_over_a_member_reads_the_group(qtbot: QtBot) -> None:
    """A group's member is dragged as the group: open hand over it, forbidden when the
    group's layer is locked (Group and Ungroup kickoff step 4)."""
    from snapmock.commands.group_commands import GroupItemsCommand

    scene, view, tm = _view_with_tools(qtbot)
    a = _add_rect(scene)
    b = _add_rect(scene)
    b.setPos(300, 100)
    scene.command_stack.push(GroupItemsCommand(scene, [a, b]))
    tm.activate("select")
    view.centerOn(250, 150)
    _move(view, QPointF(100, 150))  # a's left stroke
    assert _shape(view) == Shape.OpenHandCursor
    _move(view, QPointF(250, 150))  # the gap between the members
    assert _shape(view) == Shape.ArrowCursor
    _press(view, QPointF(100, 150))
    assert _shape(view) == Shape.ClosedHandCursor
    _release(view, QPointF(100, 150))
    assert tm._selection_manager.items == [a.parentItem()]  # noqa: SLF001
    layer = scene.layer_manager.active_layer
    assert layer is not None
    tm._selection_manager.deselect_all()  # noqa: SLF001
    scene.layer_manager.set_locked(layer.layer_id, True)
    _move(view, QPointF(300, 150))  # b's left stroke
    assert _shape(view) == Shape.ForbiddenCursor


def test_rotate_handle_carries_the_rotation_cursor(qtbot: QtBot) -> None:
    scene, _view, _tm = _view_with_tools(qtbot)
    handles = TransformHandles(scene)
    rotate = handles._handles[HandlePosition.ROTATE]  # noqa: SLF001
    assert rotate.cursor().shape() == Shape.BitmapCursor
    assert rotate.cursor().pixmap().cacheKey() == cursors.rotate_cursor().pixmap().cacheKey()
    corner = handles._handles[HandlePosition.TOP_LEFT]  # noqa: SLF001
    assert corner.cursor().shape() == Shape.SizeFDiagCursor


def test_text_tool_hover_highlighted_ibeam_over_text_and_forbidden_when_locked(
    qtbot: QtBot,
) -> None:
    scene, view, tm = _view_with_tools(qtbot)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = TextItem()
    item.text = "Hello"
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    tm.activate("text")
    view.centerOn(150, 150)
    assert _shape(view) == Shape.IBeamCursor
    inside = item.sceneBoundingRect().center()
    _move(view, inside)
    vp = view.viewport()
    assert vp is not None
    assert _shape(view) == Shape.BitmapCursor
    assert vp.cursor().pixmap().cacheKey() == cursors.text_hover_cursor().pixmap().cacheKey()
    _move(view, QPointF(20, 20))
    assert _shape(view) == Shape.IBeamCursor
    scene.layer_manager.set_locked(layer.layer_id, True)
    _move(view, inside)
    assert _shape(view) == Shape.ForbiddenCursor


def test_zoom_tool_magnifier_and_alt_minus(qtbot: QtBot) -> None:
    _scene, view, tm = _view_with_tools(qtbot)
    tm.activate("zoom")
    vp = view.viewport()
    assert vp is not None
    assert vp.cursor().pixmap().cacheKey() == cursors.zoom_in_cursor().pixmap().cacheKey()
    tm.handle_key_press(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier)
    )
    assert vp.cursor().pixmap().cacheKey() == cursors.zoom_out_cursor().pixmap().cacheKey()
    tm.handle_key_release(
        QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier)
    )
    assert vp.cursor().pixmap().cacheKey() == cursors.zoom_in_cursor().pixmap().cacheKey()


def test_eyedropper_and_raster_select_cursors(qtbot: QtBot) -> None:
    _scene, view, tm = _view_with_tools(qtbot)
    vp = view.viewport()
    assert vp is not None
    tm.activate("eyedropper")
    assert vp.cursor().pixmap().cacheKey() == cursors.eyedropper_cursor().pixmap().cacheKey()
    tm.activate("raster_select")
    assert vp.cursor().pixmap().cacheKey() == cursors.raster_select_cursor().pixmap().cacheKey()


def test_pan_tool_open_and_closed_hand_on_the_viewport(qtbot: QtBot) -> None:
    _scene, view, tm = _view_with_tools(qtbot)
    tm.activate("pan")
    assert _shape(view) == Shape.OpenHandCursor
    _press(view, QPointF(50, 50))
    assert _shape(view) == Shape.ClosedHandCursor
    _release(view, QPointF(60, 60))
    assert _shape(view) == Shape.OpenHandCursor


def test_alt_with_the_zoom_tool_is_zoom_out_not_the_momentary_eyedropper(
    main_window: MainWindow,
) -> None:
    main_window.tool_manager.activate("zoom")
    main_window.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier)
    )
    assert main_window.tool_manager.active_tool_id == "zoom"
    main_window.keyReleaseEvent(
        QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier)
    )
    assert main_window.tool_manager.active_tool_id == "zoom"


def test_external_image_drag_is_a_copy(qtbot: QtBot, tmp_path: object) -> None:
    _scene, view, _tm = _view_with_tools(qtbot)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("/tmp/picture.png")])
    actions = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    enter = QDragEnterEvent(
        QPoint(10, 10), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    view.dragEnterEvent(enter)
    assert enter.isAccepted()
    assert enter.dropAction() == Qt.DropAction.CopyAction
    move = QDragMoveEvent(
        QPoint(20, 20), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    view.dragMoveEvent(move)
    assert move.dropAction() == Qt.DropAction.CopyAction


def test_select_tool_forbidden_over_a_locked_item_and_its_handles(qtbot: QtBot) -> None:
    """The item lock (Doug's decision B of 09-25-26): a locked item can be clicked but
    not dragged, so the pointer over it, over its selection frame, and over its handles
    is the forbidden cursor, and the handles draw locked."""
    from snapmock.ui.transform_handles import LOCKED_HANDLE_FILL

    scene, view, tm = _view_with_tools(qtbot)
    item = _add_rect(scene)
    item.locked = True
    tm.activate("select")
    view.centerOn(150, 150)
    on_stroke = QPointF(100, 150)
    _move(view, on_stroke)
    assert _shape(view) == Shape.ForbiddenCursor
    _press(view, on_stroke)
    _release(view, on_stroke)
    assert tm._selection_manager.items == [item]  # noqa: SLF001
    tool = tm.active_tool
    assert isinstance(tool, SelectTool) and tool._handles is not None  # noqa: SLF001
    assert tool._handles.locked  # noqa: SLF001
    corner = tool._handles._handles[HandlePosition.TOP_LEFT]  # noqa: SLF001
    assert corner.brush().color() == LOCKED_HANDLE_FILL
    _move(view, tool._handles.current_rect.bottomRight())  # noqa: SLF001
    assert _shape(view) == Shape.ForbiddenCursor
    _move(view, QPointF(150, 150))  # the frame's interior
    assert _shape(view) == Shape.ForbiddenCursor
    _move(view, QPointF(20, 20))
    assert _shape(view) == Shape.ArrowCursor
    # Unlocked through a command, as the checkbox and the context-menu row do it, the
    # handles are live again at once: the stroke point is the middle-left handle
    from snapmock.commands.modify_property import ModifyPropertyCommand

    scene.command_stack.push(ModifyPropertyCommand(item, "locked", True, False))
    assert not tool._handles.locked  # noqa: SLF001
    _move(view, on_stroke)
    assert _shape(view) == Shape.SizeHorCursor
    # Leaving a handle item, Qt restores the cursor it saved on entering; the next move
    # of a real pointer sets the tool's cursor again, so the test sends two
    _move(view, QPointF(135, 110))  # the top stroke, clear of the handles
    _move(view, QPointF(136, 110))
    assert _shape(view) == Shape.OpenHandCursor


def test_text_tool_forbidden_over_a_locked_text_item_and_its_click_makes_no_box(
    qtbot: QtBot,
) -> None:
    scene, view, tm = _view_with_tools(qtbot)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = TextItem()
    item.text = "Hello"
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    item.locked = True
    tm.activate("text")
    view.centerOn(150, 150)
    inside = item.sceneBoundingRect().center()
    _move(view, inside)
    assert _shape(view) == Shape.ForbiddenCursor
    tool = tm.active_tool
    assert isinstance(tool, TextTool)
    _press(view, inside)
    assert tool._editing_item is None  # noqa: SLF001
    assert tool._drag_preview is None  # noqa: SLF001
    _release(view, inside)
    assert len(scene.annotation_items()) == 1
