"""Navigation shortcuts of General UI PRD 12.2 and 12.3: Tab cycling, Home/End, Alt eyedropper."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QKeyEvent
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.select_tool import SelectTool


@pytest.fixture()
def window(qtbot: QtBot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    w.tool_manager.activate("select")
    return w


def _key(
    key: Qt.Key, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier
) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def _release(key: Qt.Key) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)


def _add(window: MainWindow, x: float) -> RectangleItem:
    layer = window.scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 10, 10))
    item.setPos(x, 0)
    window.scene.command_stack.push(AddItemCommand(window.scene, item, layer.layer_id))
    return item


def _selected(window: MainWindow) -> list[str]:
    return [i.item_id for i in window.selection_manager.items if isinstance(i, RectangleItem)]


def test_tab_cycles_selection_through_the_active_layer(window: MainWindow) -> None:
    a, b, c = _add(window, 0), _add(window, 20), _add(window, 40)
    tool = window.tool_manager.active_tool
    assert isinstance(tool, SelectTool)
    assert tool.key_press(_key(Qt.Key.Key_Tab))
    assert _selected(window) == [a.item_id]
    tool.key_press(_key(Qt.Key.Key_Tab))
    assert _selected(window) == [b.item_id]
    tool.key_press(_key(Qt.Key.Key_Tab))
    tool.key_press(_key(Qt.Key.Key_Tab))
    assert _selected(window) == [a.item_id]  # wraps
    tool.key_press(_key(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier))
    assert _selected(window) == [c.item_id]
    window.scene.command_stack.mark_clean()


def test_tab_on_an_empty_layer_is_not_consumed(window: MainWindow) -> None:
    tool = window.tool_manager.active_tool
    assert isinstance(tool, SelectTool)
    assert tool.key_press(_key(Qt.Key.Key_Tab)) is False


def test_view_routes_tab_to_the_tool_before_focus_changes(window: MainWindow) -> None:
    a = _add(window, 0)
    assert window.view.event(_key(Qt.Key.Key_Tab)) is True
    assert _selected(window) == [a.item_id]
    window.scene.command_stack.mark_clean()


def test_home_and_end_pan_to_the_canvas_corners(window: MainWindow) -> None:
    window.resize(1200, 800)
    window.show()
    view = window.view
    view.set_zoom(100)
    window.keyPressEvent(_key(Qt.Key.Key_Home))
    origin = view.mapFromScene(0, 0)
    assert abs(origin.x()) <= 2 and abs(origin.y()) <= 2
    window.keyPressEvent(_key(Qt.Key.Key_End))
    canvas = window.scene.canvas_size
    corner = view.mapFromScene(canvas.width(), canvas.height())
    viewport = view.viewport()
    assert viewport is not None
    assert abs(corner.x() - viewport.width()) <= 2
    assert abs(corner.y() - viewport.height()) <= 2


def test_alt_is_a_momentary_eyedropper(window: MainWindow) -> None:
    window.tool_manager.activate("rectangle")
    window.keyPressEvent(_key(Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier))
    assert window.tool_manager.active_tool_id == "eyedropper"
    window.keyReleaseEvent(_release(Qt.Key.Key_Alt))
    assert window.tool_manager.active_tool_id == "rectangle"


# ---- arrow keys through the focused canvas view (end-to-end pass findings 4 and 5) ----


def test_arrow_keys_nudge_the_selection_when_the_view_has_focus(window: MainWindow) -> None:
    """A key press reaches the focused canvas view first. The view's scroll-area base
    class used to take the arrow keys and scroll, so with the canvas focused, which a
    click on an item leaves it, the arrows moved the canvas and never the item
    (Navigation PRD 2.4 and 3.5; end-to-end pass finding 5). Shift+Arrow moves one grid
    step, by Doug's decision (finding 4, option A)."""
    from PyQt6.QtTest import QTest

    window.resize(1200, 800)
    window.show()
    view = window.view
    view.set_zoom(100)
    view.set_grid_size(20)
    item = _add(window, 100)
    window.selection_manager.select(item)
    view.setFocus()
    h_bar = view.horizontalScrollBar()
    assert h_bar is not None
    scrolled = h_bar.value()
    QTest.keyClick(view, Qt.Key.Key_Right)
    assert item.pos().x() == 101
    QTest.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert item.pos().y() == 20  # from the line at 0, a whole step
    QTest.keyClick(view, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert item.pos().x() == 100  # from 101, to the line
    assert h_bar.value() == scrolled
    assert window.scene.command_stack.undo_text.endswith("Move 1 item")
    window.scene.command_stack.mark_clean()  # or the close prompt blocks the teardown


def test_arrow_keys_pan_the_canvas_from_the_view_when_nothing_is_selected(
    window: MainWindow,
) -> None:
    from PyQt6.QtTest import QTest

    window.resize(1200, 800)
    window.show()
    view = window.view
    view.set_zoom(300)  # a canvas larger than the viewport, so there is somewhere to pan
    window.selection_manager.deselect_all()
    view.setFocus()
    h_bar = view.horizontalScrollBar()
    v_bar = view.verticalScrollBar()
    assert h_bar is not None and v_bar is not None
    h_bar.setValue(200)
    v_bar.setValue(200)
    QTest.keyClick(view, Qt.Key.Key_Right)
    assert h_bar.value() == 220  # the main window's pan step, not the scroll area's
    QTest.keyClick(view, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert v_bar.value() == 300
