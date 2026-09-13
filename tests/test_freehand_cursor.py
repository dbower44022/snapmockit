"""The Freehand / Pen tool's cursors (Basic Shape PRD 9.1, 9.2; General UI PRD 6.6; Freehand
remainder decision 1, option A): the dot-variant crosshair while idle, the brush tip from
the press to the release."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.select_tool import SelectTool
from snapmock.tools.tool_manager import ToolManager
from snapmock.ui.cursors import (
    BRUSH_CURSOR_MAX,
    CURSOR_SIZE,
    brush_tip_cursor,
    dot_crosshair_cursor,
    reset_cursor_cache,
)

LEFT = Qt.MouseButton.LeftButton
ORIGIN = QPointF(200, 200)


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    reset_cursor_cache()
    return SnapScene(width=800, height=600)


def _setup(qtbot: QtBot, scene: SnapScene) -> tuple[SnapView, ToolManager, FreehandTool]:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(400, 300)
    tm = ToolManager(scene, SelectionManager(scene))
    tool = FreehandTool()
    tm.register(tool)
    tm.register(SelectTool())
    view.set_tool_manager(tm)
    tm.activate("freehand")
    return view, tm, tool


def _mouse(view: SnapView, kind: QEvent.Type, pos: QPointF) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, LEFT, LEFT, Qt.KeyboardModifier.NoModifier)


def _press(tm: ToolManager, view: SnapView, pos: QPointF) -> None:
    tm.handle_mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos))


def _move(tm: ToolManager, view: SnapView, pos: QPointF) -> None:
    tm.handle_mouse_move(_mouse(view, QEvent.Type.MouseMove, pos))


def _release(tm: ToolManager, view: SnapView, pos: QPointF) -> None:
    tm.handle_mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, pos))


def _viewport_cursor(view: SnapView) -> QCursor:
    vp = view.viewport()
    assert vp is not None
    return vp.cursor()


def _centre_colour(cursor: QCursor) -> QColor:
    image = cursor.pixmap().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


# ------------------------------------------------------------------ the two cursors


def test_the_idle_cursor_is_the_crosshair_with_a_centre_dot(qapp: QApplication) -> None:
    reset_cursor_cache()
    cursor = dot_crosshair_cursor()
    assert cursor.shape() == Qt.CursorShape.BitmapCursor
    assert cursor.pixmap().width() == CURSOR_SIZE
    assert cursor.hotSpot().x() == CURSOR_SIZE // 2 and cursor.hotSpot().y() == CURSOR_SIZE // 2
    image = cursor.pixmap().toImage()
    mid = CURSOR_SIZE // 2
    assert image.pixelColor(mid, mid).lightness() < 80  # the dot, black on its halo
    assert image.pixelColor(mid, 2).lightness() < 80  # the crosshair's arm
    assert image.pixelColor(mid, mid - 3).alpha() == 0  # the gap between arm and dot
    assert dot_crosshair_cursor() is cursor  # cached
    assert FreehandTool().cursor is cursor


def test_the_brush_tip_follows_the_width_and_the_colour_within_its_bounds(
    qapp: QApplication,
) -> None:
    reset_cursor_cache()
    red = QColor("#FF0000")
    tip = brush_tip_cursor(20, red)
    assert tip.pixmap().width() == 26 and tip.hotSpot().x() == 13
    assert _centre_colour(tip).name() == "#ff0000"
    assert brush_tip_cursor(20, red) is tip  # cached by size and colour
    assert brush_tip_cursor(20, QColor("#0000FF")) is not tip
    assert _centre_colour(brush_tip_cursor(20, QColor("#0000FF"))).name() == "#0000ff"
    half = QColor(255, 0, 0, 128)
    assert 100 <= _centre_colour(brush_tip_cursor(20, half)).alpha() <= 156
    assert brush_tip_cursor(1, red).pixmap().width() == 4 + 6  # never under 4 px
    assert brush_tip_cursor(500, red).pixmap().width() == BRUSH_CURSOR_MAX + 6  # the ceiling
    edge = brush_tip_cursor(40, red).pixmap().toImage()
    assert edge.pixelColor(23, 3).lightness() < 80  # the black outline on the circle
    halo = edge.pixelColor(23, 1)  # the white halo just outside it
    assert halo.alpha() > 0 and halo.lightness() > 200


# ------------------------------------------------------------------ on the viewport


def test_the_brush_tip_shows_from_the_press_to_the_release(qtbot: QtBot, scene: SnapScene) -> None:
    view, tm, tool = _setup(qtbot, scene)
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE  # the dot crosshair, idle
    tool.creation_defaults["stroke_width"] = 12.0
    tool.creation_defaults["stroke_color"] = QColor("#00AA00")
    _press(tm, view, ORIGIN)
    tip = _viewport_cursor(view)
    assert tip.pixmap().width() == 18 and tip.hotSpot().x() == 9
    assert _centre_colour(tip).name() == "#00aa00"
    _move(tm, view, QPointF(260, 210))
    assert _viewport_cursor(view).pixmap().width() == 18
    _release(tm, view, QPointF(260, 210))
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE
    assert tool.cursor is dot_crosshair_cursor()


def test_the_brush_tip_scales_with_the_zoom_mid_drag(qtbot: QtBot, scene: SnapScene) -> None:
    view, tm, tool = _setup(qtbot, scene)
    tool.creation_defaults["stroke_width"] = 10.0
    view.set_zoom(400)
    _press(tm, view, ORIGIN)
    assert _viewport_cursor(view).pixmap().width() == 46  # 10 px times 4, plus the halo
    view.set_zoom(200)  # Ctrl+wheel can zoom during a drag
    assert _viewport_cursor(view).pixmap().width() == 26
    view.set_zoom(3200)
    assert _viewport_cursor(view).pixmap().width() == BRUSH_CURSOR_MAX + 6
    _release(tm, view, QPointF(260, 210))
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE


def test_the_bar_changes_the_brush_tip_while_the_stroke_is_drawn(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tm, tool = _setup(qtbot, scene)
    _press(tm, view, ORIGIN)
    assert _viewport_cursor(view).pixmap().width() == 4 + 6  # the 2 px default, at the minimum
    tool.creation_defaults["stroke_width"] = 30.0
    tool.on_option_changed("stroke_width", 30.0)
    assert _viewport_cursor(view).pixmap().width() == 36
    tool.creation_defaults["stroke_color"] = QColor("#123456")
    tool.on_option_changed("stroke_color", QColor("#123456"))
    assert _centre_colour(_viewport_cursor(view)).name() == "#123456"
    tool.creation_defaults["stroke_opacity"] = 0.5
    tool.on_option_changed("stroke_opacity", 0.5)
    assert 100 <= _centre_colour(_viewport_cursor(view)).alpha() <= 156
    _release(tm, view, QPointF(260, 210))


def test_a_cancel_and_a_tool_switch_put_the_crosshair_back(qtbot: QtBot, scene: SnapScene) -> None:
    view, tm, tool = _setup(qtbot, scene)
    _press(tm, view, ORIGIN)
    _move(tm, view, QPointF(240, 220))
    assert _viewport_cursor(view).pixmap().width() == 10
    tool.cancel()
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE
    assert not scene.annotation_items()
    _press(tm, view, ORIGIN)
    _move(tm, view, QPointF(240, 220))
    assert _viewport_cursor(view).pixmap().width() == 10
    tm.activate("select")
    assert _viewport_cursor(view).shape() == Qt.CursorShape.ArrowCursor
    assert not scene.annotation_items()
    tm.activate("freehand")
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE
    # The zoom connection followed the switch: one refresh per zoom change, no stale view
    _press(tm, view, ORIGIN)
    view.set_zoom(400)
    assert _viewport_cursor(view).pixmap().width() == 14  # 2 px times 4, plus the halo
    _release(tm, view, QPointF(260, 210))


def test_a_locked_layer_leaves_the_cursor_alone(
    qtbot: QtBot, scene: SnapScene, unmet_messages: list[tuple[str, str]]
) -> None:
    view, tm, tool = _setup(qtbot, scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    layer.locked = True
    _press(tm, view, ORIGIN)
    assert unmet_messages and "unlocked active layer" in unmet_messages[-1][1]
    assert _viewport_cursor(view).pixmap().width() == CURSOR_SIZE
    assert tool.cursor is dot_crosshair_cursor()
