"""A handle resize changes a shape's own measurements and keeps its stroke width, corner
rounding, arrowheads, and blur strength (Technical Architecture PRD 3.4.2)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.arc_item import ArcItem
from snapmock.items.arrow_item import ArrowItem
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.blur_item import BlurItem
from snapmock.items.ellipse_item import EllipseItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.highlight_item import HighlightItem
from snapmock.items.line_item import LineItem
from snapmock.items.polygon_item import PolygonItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.vector_item import VectorItem
from snapmock.tools.select_tool import SelectTool, _State
from snapmock.ui.transform_handles import ROTATE_HANDLE_OFFSET


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _view_for(qtbot: QtBot, scene: SnapScene) -> SnapView:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(200, 200)
    return view


def _mouse(view: SnapView, kind: QEvent.Type, scene_pos: QPointF) -> QMouseEvent:
    vp_pos = QPointF(view.mapFromScene(scene_pos))
    button = Qt.MouseButton.LeftButton
    return QMouseEvent(kind, vp_pos, vp_pos, button, button, Qt.KeyboardModifier.NoModifier)


def _add(scene: SnapScene, item: SnapGraphicsItem, x: float, y: float) -> None:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item.setPos(x, y)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))


def _select(view: SnapView, scene: SnapScene, item: SnapGraphicsItem) -> SelectTool:
    sm = SelectionManager(scene)
    tool = SelectTool()
    tool.activate(scene, sm)
    sm.select(item)
    return tool


def _drag(view: SnapView, tool: SelectTool, start: QPointF, end: QPointF) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, start))
    assert tool._state is _State.HANDLE_DRAG
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, end))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, end))


# --- the reported case: a placed rectangle, reselected, resized from a handle ---


def test_corner_resize_changes_the_rectangle_not_its_stroke(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view_for(qtbot, scene)
    item = RectangleItem(QRectF(0, 0, 40, 20), corner_radius=6.0)
    item.stroke_width = 3.0
    _add(scene, item, 100, 100)
    tool = _select(view, scene, item)
    assert tool._handles is not None
    corner = tool._handles.current_rect.bottomRight()

    _drag(view, tool, corner, corner + QPointF(160, 30))

    assert item.transform().isIdentity()
    assert item.stroke_width == pytest.approx(3.0)
    assert item.corner_radius == pytest.approx(6.0)
    body = item.mapRectToScene(item.rect)
    assert body.left() == pytest.approx(100, abs=0.5)
    assert body.top() == pytest.approx(100, abs=0.5)
    assert body.width() == pytest.approx(200, abs=1.0)
    assert body.height() == pytest.approx(50, abs=1.0)

    scene.command_stack.undo()
    assert item.rect == QRectF(0, 0, 40, 20)
    assert item.pos() == QPointF(100, 100)
    scene.command_stack.redo()
    assert item.rect.width() == pytest.approx(body.width())
    assert item.stroke_width == pytest.approx(3.0)


def test_edge_resize_changes_one_side_only(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view_for(qtbot, scene)
    item = EllipseItem(rect=QRectF(0, 0, 80, 40))
    item.stroke_width = 4.0
    _add(scene, item, 100, 100)
    tool = _select(view, scene, item)
    assert tool._handles is not None
    frame = tool._handles.current_rect
    edge = QPointF(frame.right(), frame.center().y())

    _drag(view, tool, edge, edge + QPointF(80, 0))

    assert item.transform().isIdentity()
    assert item.stroke_width == pytest.approx(4.0)
    assert item.rect.height() == pytest.approx(40)
    assert item.rect.width() > 140


def test_a_previously_stretched_shape_keeps_its_transform(qtbot: QtBot, scene: SnapScene) -> None:
    """A rectangle stretched before this change still resizes by its measurements."""
    view = _view_for(qtbot, scene)
    item = RectangleItem(QRectF(0, 0, 50, 50))
    item.setTransform(QTransform.fromScale(2.0, 1.0))
    _add(scene, item, 100, 100)
    tool = _select(view, scene, item)
    assert tool._handles is not None
    corner = tool._handles.current_rect.bottomRight()

    _drag(view, tool, corner, corner + QPointF(100, 50))

    assert item.transform() == QTransform.fromScale(2.0, 1.0)
    assert item.rect.width() > 50


def test_a_rotated_shape_still_stretches(qtbot: QtBot, scene: SnapScene) -> None:
    """Axis-aligned handles cannot keep a rotated rectangle a rectangle (3.4.2)."""
    view = _view_for(qtbot, scene)
    item = RectangleItem(QRectF(0, 0, 60, 40))
    item.setTransform(QTransform().rotate(30))
    _add(scene, item, 150, 150)
    tool = _select(view, scene, item)
    assert tool._handles is not None
    corner = tool._handles.current_rect.bottomRight()

    _drag(view, tool, corner, corner + QPointF(40, 40))

    assert item.rect == QRectF(0, 0, 60, 40)
    assert not item.transform().isIdentity()


def test_a_rotation_drag_on_a_shape_records_the_rotation(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view_for(qtbot, scene)
    item = RectangleItem(QRectF(0, 0, 100, 60))
    _add(scene, item, 100, 100)
    tool = _select(view, scene, item)
    assert tool._handles is not None
    frame = tool._handles.current_rect
    handle = QPointF(frame.center().x(), frame.top() - ROTATE_HANDLE_OFFSET)

    _drag(view, tool, handle, handle + QPointF(80, 40))

    assert not item.transform().isIdentity()
    assert item.rect == QRectF(0, 0, 100, 60)
    scene.command_stack.undo()
    assert item.transform().isIdentity()


# --- every shape type: resize_shape moves the measurements and keeps the style ---


def _shapes() -> list[SnapGraphicsItem]:
    rect = RectangleItem(QRectF(0, 0, 100, 50), corner_radius=8.0)
    arrow = ArrowItem(line=QLineF(0, 0, 100, 50))
    arrow.head_size_custom = 20.0
    freehand = FreehandItem()
    for x, y in ((0, 0), (50, 25), (100, 50)):
        freehand.add_point(QPointF(x, y))
    highlight = HighlightItem()
    highlight.add_point(0, 0)
    highlight.add_point(100, 50)
    return [
        rect,
        EllipseItem(rect=QRectF(0, 0, 100, 50)),
        LineItem(line=QLineF(0, 0, 100, 50)),
        arrow,
        ArcItem(QPointF(0, 50), QPointF(100, 50), QPointF(50, 0)),
        PolygonItem([QPointF(0, 0), QPointF(100, 0), QPointF(50, 50)]),
        highlight,
        freehand,
        BlurItem(rect=QRectF(0, 0, 100, 50), blur_radius=12.0),
    ]


@pytest.mark.parametrize("index", range(9))
def test_resize_shape_keeps_the_style(qapp: QApplication, index: int) -> None:
    item = _shapes()[index]
    assert item.resizes_shape
    if isinstance(item, VectorItem):
        item.stroke_width = 5.0
    kept = {name: getattr(item, name) for name in item.KEPT_ON_RESIZE}
    before = item.geometry_rect()
    state = item.shape_state()

    item.resize_shape(2.0, 3.0)

    after = item.geometry_rect()
    assert after.width() == pytest.approx(before.width() * 2.0, rel=0.05)
    assert after.height() == pytest.approx(before.height() * 3.0, rel=0.05)
    for name, value in kept.items():
        assert getattr(item, name) == value, name

    item.restore_shape_state(state)
    assert item.geometry_rect() == before


def test_images_and_markers_still_stretch() -> None:
    from snapmock.items.numbered_step_item import NumberedStepItem

    assert not NumberedStepItem().resizes_shape
