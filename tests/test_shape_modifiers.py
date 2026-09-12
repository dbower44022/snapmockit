"""The shape tools' drawing modifiers (Basic Shape PRD 2.3, 9.5; Section 12).

Shift squares the Rectangle and circles the Ellipse; the centre-draw modifier — Alt,
or Ctrl as the second route of decision 4 — puts the origin at the shape's centre for
the Rectangle, the Ellipse, and the Arc; the two together give a square or a circle
centred on the press point; and Shift holds a Freehand stroke to horizontal, vertical,
and 45-degree segments from the point it was first held.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.core.path_utils import constrained_rect
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.ellipse_item import EllipseItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.tools.arc_tool import ArcTool
from snapmock.tools.base_tool import BaseTool
from snapmock.tools.ellipse_tool import EllipseTool
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.rectangle_tool import RectangleTool

NONE = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier
CTRL = Qt.KeyboardModifier.ControlModifier
LEFT = Qt.MouseButton.LeftButton

ORIGIN = QPointF(200, 200)
FAR = QPointF(300, 240)  # 100 across, 40 down: the two axes differ, so a square shows


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _setup(qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]) -> tuple[SnapView, BaseTool]:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(400, 300)
    tool = factory()
    tool.activate(scene, SelectionManager(scene))
    return view, tool


def _mouse(
    view: SnapView, kind: QEvent.Type, pos: QPointF, mods: Qt.KeyboardModifier = NONE
) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, LEFT, LEFT, mods)


def _press(tool: BaseTool, view: SnapView, pos: QPointF) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos))


def _move(tool: BaseTool, view: SnapView, pos: QPointF, mods: Qt.KeyboardModifier = NONE) -> None:
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, pos, mods))


def _release(
    tool: BaseTool, view: SnapView, pos: QPointF, mods: Qt.KeyboardModifier = NONE
) -> None:
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, pos, mods))


def _drawn(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], mods: Qt.KeyboardModifier
) -> tuple[QPointF, QPointF]:
    """Draw from ORIGIN to FAR under *mods* and report the shape's scene position and size."""
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, ORIGIN)
    _move(tool, view, FAR, mods)
    _release(tool, view, FAR, mods)
    items = [i for i in scene.annotation_items() if isinstance(i, RectangleItem | EllipseItem)]
    assert len(items) == 1
    item = items[0]
    return item.pos(), QPointF(item.rect.width(), item.rect.height())


# ---------------------------------------------------------------- the geometry helper


def test_the_helper_reads_each_modifier_combination() -> None:
    plain = constrained_rect(ORIGIN, FAR)
    assert (plain.topLeft(), plain.width(), plain.height()) == (ORIGIN, 100.0, 40.0)

    square = constrained_rect(ORIGIN, FAR, square=True)
    assert (square.topLeft(), square.width(), square.height()) == (ORIGIN, 100.0, 100.0)

    centred = constrained_rect(ORIGIN, FAR, from_centre=True)
    assert centred.center() == ORIGIN
    assert (centred.width(), centred.height()) == (200.0, 80.0)

    both = constrained_rect(ORIGIN, FAR, square=True, from_centre=True)
    assert both.center() == ORIGIN
    assert (both.width(), both.height()) == (200.0, 200.0)


def test_the_square_follows_the_cursor_into_every_quadrant() -> None:
    for dx, dy in ((100, 40), (-100, 40), (100, -40), (-100, -40)):
        target = QPointF(ORIGIN.x() + dx, ORIGIN.y() + dy)
        rect = constrained_rect(ORIGIN, target, square=True)
        assert rect.width() == rect.height() == 100.0
        # The pressed corner stays put; the square grows the way the cursor went
        assert ORIGIN in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight())


# ------------------------------------------------------- Shift and the centre modifier


def test_shift_squares_the_rectangle(qtbot: QtBot, scene: SnapScene) -> None:
    pos, size = _drawn(qtbot, scene, RectangleTool, SHIFT)
    assert size == QPointF(100.0, 100.0)
    assert pos == ORIGIN


def test_shift_circles_the_ellipse(qtbot: QtBot, scene: SnapScene) -> None:
    pos, size = _drawn(qtbot, scene, EllipseTool, SHIFT)
    assert size == QPointF(100.0, 100.0)
    assert pos == ORIGIN


@pytest.mark.parametrize("modifier", [ALT, CTRL])
@pytest.mark.parametrize("factory", [RectangleTool, EllipseTool])
def test_the_centre_modifier_grows_the_shape_from_the_press_point(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], modifier: Qt.KeyboardModifier
) -> None:
    """Decision 4, option B: Alt is the convention and Ctrl the second route, because
    Alt plus a mouse button never reaches the canvas on this desktop."""
    pos, size = _drawn(qtbot, scene, factory, modifier)
    assert size == QPointF(200.0, 80.0)
    assert pos == QPointF(ORIGIN.x() - 100, ORIGIN.y() - 40)


@pytest.mark.parametrize("modifier", [ALT, CTRL])
@pytest.mark.parametrize("factory", [RectangleTool, EllipseTool])
def test_shift_and_the_centre_modifier_together(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], modifier: Qt.KeyboardModifier
) -> None:
    pos, size = _drawn(qtbot, scene, factory, SHIFT | modifier)
    assert size == QPointF(200.0, 200.0)
    assert pos == QPointF(ORIGIN.x() - 100, ORIGIN.y() - 100)


def test_a_modifier_pressed_and_released_mid_drag_takes_effect_from_that_moment(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """The tools recompute from the press point on every move, so nothing restarts."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, ORIGIN)

    _move(tool, view, FAR)
    item = tool._item  # noqa: SLF001
    assert item is not None
    assert (item.rect.width(), item.rect.height()) == (100.0, 40.0)

    _move(tool, view, FAR, SHIFT)
    assert (item.rect.width(), item.rect.height()) == (100.0, 100.0)

    _move(tool, view, FAR, SHIFT | CTRL)
    assert (item.rect.width(), item.rect.height()) == (200.0, 200.0)

    _move(tool, view, FAR)
    assert (item.rect.width(), item.rect.height()) == (100.0, 40.0)
    assert item.pos() == ORIGIN


@pytest.mark.parametrize("modifier", [ALT, CTRL])
def test_the_arc_chord_grows_both_ways_from_the_press_point(
    qtbot: QtBot, scene: SnapScene, modifier: Qt.KeyboardModifier
) -> None:
    """2.3 lists the Arc under the centre modifier and Section 7 does not say what it
    does: the press point becomes the chord's midpoint (notes Section 6)."""
    view, tool = _setup(qtbot, scene, ArcTool)
    _press(tool, view, ORIGIN)
    _move(tool, view, FAR, modifier)

    preview = tool.preview
    assert preview is not None
    assert preview.end_point == QPointF(200.0, 80.0)
    assert preview.pos() == QPointF(ORIGIN.x() - 100, ORIGIN.y() - 40)
    # The chord's midpoint is where the press landed
    assert preview.mapToScene(preview.end_point / 2.0) == ORIGIN


def test_the_arc_takes_shift_and_the_centre_modifier_together(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, ArcTool)
    _press(tool, view, ORIGIN)
    _move(tool, view, QPointF(300, 300), SHIFT | CTRL)

    preview = tool.preview
    assert preview is not None
    # Shift holds the chord at 45 degrees and the centre modifier doubles it
    assert preview.end_point.x() == pytest.approx(preview.end_point.y())
    assert preview.mapToScene(preview.end_point / 2.0) == ORIGIN


def test_the_curvature_step_follows_the_moved_chord(qtbot: QtBot, scene: SnapScene) -> None:
    """The second step measures from the item's own position, not the press point, which
    the centre modifier moves away from it."""
    view, tool = _setup(qtbot, scene, ArcTool)
    _press(tool, view, ORIGIN)
    _move(tool, view, FAR, CTRL)
    _release(tool, view, FAR, CTRL)

    preview = tool.preview
    assert preview is not None
    flat = QPointF(preview.control_point)
    tool.mouse_move(
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(view.mapFromScene(QPointF(200, 120))),
            QPointF(view.mapFromScene(QPointF(200, 120))),
            LEFT,
            Qt.MouseButton.NoButton,
            NONE,
        )
    )
    assert preview.control_point != flat


# --------------------------------------------- the Freehand's straight segments (9.5)


def _freehand(scene: SnapScene) -> FreehandItem:
    items = [i for i in scene.annotation_items() if isinstance(i, FreehandItem)]
    assert len(items) == 1
    return items[0]


def test_shift_holds_a_freehand_stroke_to_a_straight_segment(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, FreehandTool)
    _press(tool, view, ORIGIN)
    # A near-horizontal drag with Shift held lands exactly on the horizontal
    _move(tool, view, QPointF(260, 205), SHIFT)
    _move(tool, view, QPointF(300, 208), SHIFT)

    item = tool._item  # noqa: SLF001
    assert item is not None
    points = item.path_points
    assert len(points) == 2  # the anchor and one replaced segment end
    # Exactly horizontal, at the cursor's own distance from the anchor, as the Line and
    # Arrow tools' Shift already works
    assert points[-1].y() == pytest.approx(0.0, abs=1e-6)
    assert points[-1].x() == pytest.approx(100.32, abs=0.01)


def test_the_shift_segment_snaps_to_the_vertical_and_the_diagonal(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, FreehandTool)
    _press(tool, view, ORIGIN)

    _move(tool, view, QPointF(205, 300), SHIFT)
    item = tool._item  # noqa: SLF001
    assert item is not None
    assert item.path_points[-1].x() == pytest.approx(0.0, abs=1e-6)

    _move(tool, view, QPointF(300, 290), SHIFT)
    end = item.path_points[-1]
    assert end.x() == pytest.approx(end.y())


def test_a_stroke_mixes_a_curve_and_a_straight_segment(qtbot: QtBot, scene: SnapScene) -> None:
    """9.5's reason for existing: a freehand run, then a precise straight one."""
    view, tool = _setup(qtbot, scene, FreehandTool)
    _press(tool, view, ORIGIN)
    for y in (210, 225, 245):
        _move(tool, view, QPointF(ORIGIN.x() + (y - 200) // 2, y))
    curve_points = len(tool._item.path_points)  # noqa: SLF001
    assert curve_points == 4

    # Shift now: every further move replaces one segment rather than adding to the curve
    for x in (280, 320, 360):
        _move(tool, view, QPointF(x, 250), SHIFT)
    item = tool._item  # noqa: SLF001
    assert item is not None
    assert len(item.path_points) == curve_points + 1
    assert item.path_points[-1].y() == pytest.approx(item.path_points[curve_points - 1].y())

    # Releasing Shift resumes freehand from the straight segment's end
    _move(tool, view, QPointF(370, 270))
    assert len(item.path_points) == curve_points + 2

    _release(tool, view, QPointF(370, 270))
    assert _freehand(scene) is not None


def test_the_snapshot_restores_the_stroke_and_stays_usable(qapp: QApplication) -> None:
    item = FreehandItem()
    for i in range(10):
        item.add_point(QPointF(float(i), float(i)))
    snapshot = item.preview_snapshot()

    item.add_point(QPointF(99.0, 99.0))
    assert len(item.path_points) == 11

    item.restore_preview(snapshot)
    assert len(item.path_points) == 10
    assert item.path_points[-1] == QPointF(9.0, 9.0)

    # Restoring twice from one snapshot works: the Shift move does it on every move
    item.add_point(QPointF(50.0, 50.0))
    item.restore_preview(snapshot)
    assert len(item.path_points) == 10


def test_the_shift_segment_costs_little_per_move(qtbot: QtBot, scene: SnapScene) -> None:
    """A Shift move restores the snapshot taken when Shift was first held, which is a
    list copy rather than a replay. A loose ceiling; the figure is in the notes."""
    view, tool = _setup(qtbot, scene, FreehandTool)
    _press(tool, view, ORIGIN)
    for i in range(500):
        _move(tool, view, QPointF(200.0 + i * 0.2, 200.0 + (i % 7)))

    start = time.perf_counter()
    for i in range(30):
        _move(tool, view, QPointF(400.0 + i, 260.0), SHIFT)
    per_move_ms = (time.perf_counter() - start) * 1000.0 / 30.0

    assert per_move_ms < 16.7, f"{per_move_ms:.2f} ms per move over a 500-point stroke"
