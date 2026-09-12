"""The dimension tooltip, the constrain icon, and the centre marker (Basic Shape PRD 2.4).

Decision 1 of the shape tools' shared drawing work, option A: the three are a widget over
the canvas view's viewport, as the Eyedropper's loupe is, so the offset and the
repositioning are screen-pixel arithmetic on the viewport rectangle, shared with the loupe,
and nothing of them can reach a render of the scene.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsProxyWidget
from pytestqt.qtbot import QtBot

from snapmock.config.constants import PolygonMode
from snapmock.core.render_engine import RenderEngine
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.main_window import MainWindow
from snapmock.tools.arc_tool import ArcTool
from snapmock.tools.arrow_tool import ArrowTool
from snapmock.tools.base_tool import BaseTool
from snapmock.tools.ellipse_tool import EllipseTool
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.line_tool import LineTool
from snapmock.tools.polygon_tool import PolygonTool
from snapmock.tools.rectangle_tool import RectangleTool
from snapmock.ui.dimension_overlay import (
    CENTRE_MARKER_SIZE,
    TOOLTIP_CURSOR_OFFSET,
    DimensionOverlay,
    existing_dimension_overlay,
    length_angle_text,
    marker_position,
    tooltip_position,
)
from snapmock.ui.loupe_overlay import (
    LOUPE_CURSOR_OFFSET,
    beside_cursor,
    loupe_position,
    loupe_size,
)

NONE = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton

VIEWPORT = QRect(0, 0, 800, 600)
SIZE = (120, 24)


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _setup(qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]) -> tuple[SnapView, BaseTool]:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(300, 200)
    tool = factory()
    tool.activate(scene, SelectionManager(scene))
    return view, tool


def _mouse(
    view: SnapView,
    kind: QEvent.Type,
    pos: QPointF,
    modifiers: Qt.KeyboardModifier = NONE,
    buttons: Qt.MouseButton = LEFT,
) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, LEFT, buttons, modifiers)


def _press(tool: BaseTool, view: SnapView, pos: QPointF, mods: Qt.KeyboardModifier = NONE) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos, mods))


def _move(
    tool: BaseTool,
    view: SnapView,
    pos: QPointF,
    mods: Qt.KeyboardModifier = NONE,
    buttons: Qt.MouseButton = LEFT,
) -> None:
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, pos, mods, buttons))


def _release(tool: BaseTool, view: SnapView, pos: QPointF) -> None:
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, pos))


def _overlay(view: SnapView) -> DimensionOverlay:
    viewport = view.viewport()
    assert viewport is not None
    overlay = existing_dimension_overlay(viewport)
    assert overlay is not None
    return overlay


def _showing(view: SnapView) -> DimensionOverlay:
    overlay = _overlay(view)
    assert not overlay.isHidden()
    return overlay


def _hidden(view: SnapView) -> bool:
    viewport = view.viewport()
    assert viewport is not None
    overlay = existing_dimension_overlay(viewport)
    return overlay is None or (overlay.isHidden() and overlay.centre_marker.isHidden())


# --------------------------------------------------------------- geometry (2.4)


def test_the_tooltip_sits_15_by_15_px_from_the_cursor() -> None:
    assert TOOLTIP_CURSOR_OFFSET == 15  # noqa: PLR2004
    assert tooltip_position(QPoint(400, 300), SIZE, VIEWPORT) == QPoint(415, 315)


def test_the_tooltip_is_repositioned_at_each_viewport_edge() -> None:
    width, height = SIZE
    # The right edge: it goes to the left of the cursor
    right = tooltip_position(QPoint(780, 300), SIZE, VIEWPORT)
    assert right == QPoint(780 - 15 - width, 315)
    # The bottom edge: it goes above the cursor
    bottom = tooltip_position(QPoint(400, 590), SIZE, VIEWPORT)
    assert bottom == QPoint(415, 590 - 15 - height)
    # The bottom-right corner: both at once
    corner = tooltip_position(QPoint(790, 595), SIZE, VIEWPORT)
    assert corner == QPoint(790 - 15 - width, 595 - 15 - height)
    # The left and top edges: the offset already keeps it inside
    assert tooltip_position(QPoint(0, 0), SIZE, VIEWPORT) == QPoint(15, 15)
    # A viewport too small for either side clamps it inside, never negative
    tiny = tooltip_position(QPoint(40, 20), SIZE, QRect(0, 0, 130, 40))
    assert tiny.x() >= 0 and tiny.y() >= 0
    assert tiny.x() + width <= 130 and tiny.y() + height <= 40  # noqa: PLR2004


def test_the_loupe_and_the_tooltip_share_one_edge_rule() -> None:
    """Decision 1: the screen-edge arithmetic is factored out of the loupe, not copied."""
    for cursor in (QPoint(400, 400), QPoint(790, 400), QPoint(400, 10), QPoint(5, 5)):
        assert loupe_position(cursor, VIEWPORT) == beside_cursor(
            cursor, loupe_size(), VIEWPORT, LOUPE_CURSOR_OFFSET, above=True
        )


def test_the_marker_is_centred_on_the_origin() -> None:
    at = marker_position(QPoint(200, 150))
    assert at + QPoint(CENTRE_MARKER_SIZE // 2, CENTRE_MARKER_SIZE // 2) == QPoint(200, 150)


def test_the_length_and_angle_read_as_the_prd_words_them() -> None:
    assert length_angle_text(245.0, 0.0) == "L: 245px ∠ 0.0°"
    assert length_angle_text(100.0, -100.0) == "L: 141px ∠ 45.0°"
    assert length_angle_text(-100.0, 0.0) == "L: 100px ∠ 180.0°"
    assert length_angle_text(0.0, 0.0) == "L: 0px ∠ 0.0°"


# --------------------------------------------------------------- the text per tool


@pytest.mark.parametrize(
    ("factory", "mods", "text"),
    [
        (LineTool, NONE, "L: 100px ∠ 0.0°"),
        (ArrowTool, NONE, "L: 100px ∠ 0.0°"),
        (RectangleTool, NONE, "W: 100 H: 60"),
        (RectangleTool, SHIFT, "W: 100 H: 100"),
        (EllipseTool, NONE, "W: 100 H: 60"),
        (EllipseTool, SHIFT, "D: 100"),
        (FreehandTool, NONE, "Drawing…"),
    ],
)
def test_each_drag_drawn_tool_shows_its_own_measurements(
    qtbot: QtBot,
    scene: SnapScene,
    factory: type[BaseTool],
    mods: Qt.KeyboardModifier,
    text: str,
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 100 if factory in (LineTool, ArrowTool) else 160), mods)

    overlay = _showing(view)
    assert overlay.text == text
    assert tool.drawing_measurement == (text,)


def test_the_line_reads_its_angle_counter_clockwise(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, LineTool)
    _press(tool, view, QPointF(100, 200))
    _move(tool, view, QPointF(200, 100))
    assert _showing(view).text == "L: 141px ∠ 45.0°"


def test_the_arc_shows_its_chord_then_its_curve(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, ArcTool)
    _press(tool, view, QPointF(100, 200))
    _move(tool, view, QPointF(300, 200))
    assert _showing(view).text == "L: 200px ∠ 0.0°"

    _release(tool, view, QPointF(300, 200))
    assert _showing(view).text == "Arc: 200px Bulge: 0px"
    _move(tool, view, QPointF(230, 120), buttons=NO_BUTTON)
    assert _showing(view).text.endswith("Bulge: 80px")
    # The status bar hint carries the same values the tooltip shows
    assert tool.status_hint.startswith(_showing(view).text + " | ")


def test_the_polygon_shows_its_vertices_or_its_sides_and_radius(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, PolygonTool)
    for pos in (QPointF(100, 100), QPointF(200, 100)):
        _press(tool, view, pos)
        _release(tool, view, pos)
    _move(tool, view, QPointF(200, 200), buttons=NO_BUTTON)
    assert _showing(view).text == "Vertices: 2"
    assert tool.status_hint.startswith("Vertices: 2 | ")
    tool.cancel()
    assert _hidden(view)

    tool.creation_defaults["polygon_mode"] = PolygonMode.REGULAR
    _press(tool, view, QPointF(300, 300))
    _move(tool, view, QPointF(350, 300))
    assert _showing(view).text == "Sides: 5 R: 50px"
    assert tool.status_hint.startswith("Sides: 5 | R: 50px | ")


def test_the_tooltip_follows_the_cursor(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    for end in (QPointF(200, 160), QPointF(260, 220)):
        _move(tool, view, end)
        cursor = view.mapFromScene(end)
        assert _showing(view).pos() == cursor + QPoint(15, 15)


# --------------------------------------------------------------- the icon and the marker


def test_the_constrain_icon_appears_while_shift_is_held(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    plain = _showing(view)
    assert not plain.constrained
    plain_width = plain.width()

    _move(tool, view, QPointF(200, 160), SHIFT)
    assert _showing(view).constrained
    assert _showing(view).width() > plain_width  # room for the icon beside the text

    _move(tool, view, QPointF(200, 160))
    assert not _showing(view).constrained


def test_the_arc_shows_no_constrain_icon_where_shift_holds_nothing(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, ArcTool)
    _press(tool, view, QPointF(100, 200))
    _move(tool, view, QPointF(300, 200), SHIFT)
    assert _showing(view).constrained
    _release(tool, view, QPointF(300, 200))
    _move(tool, view, QPointF(230, 120), SHIFT, NO_BUTTON)
    assert not _showing(view).constrained


@pytest.mark.parametrize("key", [CTRL, ALT])
@pytest.mark.parametrize("factory", [RectangleTool, EllipseTool, ArcTool])
def test_the_centre_marker_sits_on_the_origin_point(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], key: Qt.KeyboardModifier
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    origin = QPointF(150, 150)
    _press(tool, view, origin)
    _move(tool, view, QPointF(220, 200))
    assert _showing(view).centre_marker.isHidden()

    _move(tool, view, QPointF(220, 200), key)
    marker = _showing(view).centre_marker
    assert not marker.isHidden()
    half = CENTRE_MARKER_SIZE // 2
    assert marker.pos() + QPoint(half, half) == view.mapFromScene(origin)

    _move(tool, view, QPointF(220, 200))
    assert marker.isHidden()


@pytest.mark.parametrize("factory", [LineTool, ArrowTool, FreehandTool])
def test_no_centre_marker_where_the_tool_draws_from_no_centre(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]
) -> None:
    """2.3 lists the centre-draw modifier for the Rectangle, the Ellipse, and the Arc."""
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(150, 150))
    _move(tool, view, QPointF(220, 200), CTRL)
    assert _showing(view).centre_marker.isHidden()


def test_the_marker_survives_a_modifier_held_through_the_whole_drag(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """The marker is on the press point and the tooltip on the cursor: two places."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(150, 150), CTRL)
    for end in (QPointF(180, 170), QPointF(240, 230)):
        _move(tool, view, end, CTRL)
    overlay = _showing(view)
    half = CENTRE_MARKER_SIZE // 2
    assert overlay.centre_marker.pos() + QPoint(half, half) == view.mapFromScene(QPointF(150, 150))
    assert overlay.pos() == view.mapFromScene(QPointF(240, 230)) + QPoint(15, 15)
    assert overlay.text == "W: 180 H: 160"


# --------------------------------------------------------------- its lifetime


@pytest.mark.parametrize("factory", [RectangleTool, LineTool, FreehandTool])
def test_the_tooltip_goes_when_the_shape_is_released(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(100, 100), CTRL)
    _move(tool, view, QPointF(200, 160), CTRL)
    _showing(view)
    _release(tool, view, QPointF(200, 160))
    assert _hidden(view)


def test_escape_and_cancel_take_the_tooltip_and_the_marker(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, EllipseTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160), CTRL)
    assert not _showing(view).centre_marker.isHidden()
    assert tool.handle_escape()
    assert _hidden(view)

    arc_view, arc = _setup(qtbot, SnapScene(width=800, height=600), ArcTool)
    _press(arc, arc_view, QPointF(100, 100))
    _move(arc, arc_view, QPointF(200, 160))
    _showing(arc_view)
    arc.cancel()
    assert _hidden(arc_view)


def test_confirming_an_arc_and_a_polygon_takes_the_tooltip(qtbot: QtBot, scene: SnapScene) -> None:
    view, arc = _setup(qtbot, scene, ArcTool)
    _press(arc, view, QPointF(100, 200))
    _move(arc, view, QPointF(300, 200))
    _release(arc, view, QPointF(300, 200))
    _showing(view)
    _press(arc, view, QPointF(230, 120))  # the click that confirms the curvature
    assert _hidden(view)

    polygon_view, polygon = _setup(qtbot, SnapScene(width=800, height=600), PolygonTool)
    polygon.creation_defaults["polygon_mode"] = PolygonMode.REGULAR
    _press(polygon, polygon_view, QPointF(300, 300))
    _move(polygon, polygon_view, QPointF(350, 300))
    _showing(polygon_view)
    _release(polygon, polygon_view, QPointF(350, 300))
    assert _hidden(polygon_view)


def test_a_tool_switch_during_a_drag_takes_the_tooltip(main_window: MainWindow) -> None:
    view = main_window.view
    main_window.tool_manager.activate("rectangle")
    tool = main_window.tool_manager.active_tool
    assert tool is not None
    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(200, 160), CTRL)
    _showing(view)

    main_window.tool_manager.activate("ellipse")
    assert _hidden(view)


def test_the_tooltip_hides_when_the_pointer_leaves_the_viewport(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160), CTRL)
    viewport = view.viewport()
    assert viewport is not None
    QApplication.sendEvent(viewport, QEvent(QEvent.Type.Leave))
    assert _hidden(view)


def test_every_tool_shares_the_one_overlay(qtbot: QtBot, scene: SnapScene) -> None:
    view, rectangle = _setup(qtbot, scene, RectangleTool)
    line = LineTool()
    line.activate(scene, SelectionManager(scene))
    for tool in (rectangle, line):
        _press(tool, view, QPointF(100, 100))
        _move(tool, view, QPointF(200, 160))
        _release(tool, view, QPointF(200, 160))
    viewport = view.viewport()
    assert viewport is not None
    assert len(viewport.findChildren(DimensionOverlay)) == 1


def test_the_overlay_carries_accessible_names_and_takes_no_input(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160), CTRL)
    overlay = _showing(view)
    for widget in (overlay, overlay.centre_marker):
        assert widget.accessibleName()
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert widget.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_the_tooltip_never_reaches_a_render_of_the_scene(qtbot: QtBot, scene: SnapScene) -> None:
    """2.4's feedback is an overlay on the viewport, never a scene item."""
    scene.set_background_color(QColor("#FFFFFF"))
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160), SHIFT | CTRL)
    overlay = _showing(view)
    assert overlay.parentWidget() is view.viewport()
    assert overlay.centre_marker.parentWidget() is view.viewport()
    assert not any(isinstance(i, QGraphicsProxyWidget) for i in scene.items())
    # Where the tooltip is drawn over the canvas, an export shows the canvas colour
    at = view.mapToScene(overlay.geometry().center())
    export = RenderEngine(scene).render_to_image()
    assert export.pixelColor(int(at.x()), int(at.y())) == QColor("#FFFFFF")


# --------------------------------------------------------------- its cost per move


def test_the_tooltip_costs_little_per_mouse_move(qtbot: QtBot, scene: SnapScene) -> None:
    """Section 12's 60 frames a second: the tooltip shares the per-move budget the loupe
    measured at 0.36 to 0.45 ms (Eyedropper and Blur performance notes 4.1). The figure
    measured on this machine is in the notes; the ceiling here is a whole frame."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(101, 101))
    events = [
        _mouse(
            view, QEvent.Type.MouseMove, QPointF(110 + i, 120 + (i % 40)), SHIFT if i % 2 else CTRL
        )
        for i in range(300)
    ]
    start = time.perf_counter()
    for event in events:
        tool._show_drawing_feedback(event)  # noqa: SLF001
    per_move_ms = (time.perf_counter() - start) * 1000.0 / len(events)
    assert per_move_ms < 16.7  # noqa: PLR2004


def test_a_nearly_level_line_never_reads_a_negative_zero() -> None:
    assert length_angle_text(200.0, 0.1) == "L: 200px ∠ 0.0°"
    assert length_angle_text(-200.0, 0.1) == "L: 200px ∠ 180.0°"
