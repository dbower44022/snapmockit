"""The 70 percent preview, the guide lines to the rulers, and the Drawing hints.

Basic Shape PRD 2.4's first and last bullets, and the Status Bar Hints tables of 3.7, 4.8,
5.7, 6.7, and 9.11. The guide lines follow decision 3 of the shape tools' shared drawing
work (option A): drawn in the view's foreground pass from the shape's own edges while a
drag lasts, and only while the rulers are visible.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.config.constants import DRAWING_PREVIEW_OPACITY, PolygonMode
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

NONE = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton

DRAG_TOOLS: tuple[type[BaseTool], ...] = (
    RectangleTool,
    EllipseTool,
    LineTool,
    ArrowTool,
    FreehandTool,
)


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


def _press(tool: BaseTool, view: SnapView, pos: QPointF) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos))


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


def _preview(tool: BaseTool) -> object:
    item = getattr(tool, "_item", None)
    assert item is not None
    return item


# --------------------------------------------------------------- the 70 percent preview


@pytest.mark.parametrize("factory", DRAG_TOOLS)
def test_the_preview_is_drawn_at_70_percent_and_committed_at_full(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    preview = _preview(tool)
    assert preview.opacity() == pytest.approx(DRAWING_PREVIEW_OPACITY)  # type: ignore[attr-defined]

    _release(tool, view, QPointF(200, 160))
    (item,) = scene.annotation_items()
    assert item is preview
    assert item.opacity() == pytest.approx(1.0)


def test_the_arc_and_the_polygon_preview_at_70_percent_too(qtbot: QtBot, scene: SnapScene) -> None:
    view, arc = _setup(qtbot, scene, ArcTool)
    _press(arc, view, QPointF(100, 200))
    _move(arc, view, QPointF(300, 200))
    _release(arc, view, QPointF(300, 200))
    preview = arc.preview
    assert preview is not None and preview.opacity() == pytest.approx(0.7)
    _press(arc, view, QPointF(230, 120))
    assert preview.opacity() == pytest.approx(1.0)

    polygon = PolygonTool()
    polygon.activate(scene, SelectionManager(scene))
    polygon.creation_defaults["polygon_mode"] = PolygonMode.REGULAR
    _press(polygon, view, QPointF(400, 300))
    _move(polygon, view, QPointF(450, 300))
    shape = polygon.preview
    assert shape is not None and shape.opacity() == pytest.approx(0.7)
    _release(polygon, view, QPointF(450, 300))
    assert shape.opacity() == pytest.approx(1.0)
    assert {i.opacity() for i in scene.annotation_items()} == {1.0}


def test_the_preview_keeps_its_own_opacity_in_proportion(qtbot: QtBot, scene: SnapScene) -> None:
    """The dimming is of the item's own opacity, and that opacity is what is saved."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(100, 100))
    preview = _preview(tool)
    tool._end_preview()  # noqa: SLF001
    preview.setOpacity(0.5)  # type: ignore[attr-defined]
    tool._start_preview(preview)  # type: ignore[arg-type]  # noqa: SLF001
    assert preview.opacity() == pytest.approx(0.35)  # type: ignore[attr-defined]
    tool._end_preview()  # noqa: SLF001
    assert preview.opacity() == pytest.approx(0.5)  # type: ignore[attr-defined]


# --------------------------------------------------------------- the Drawing hints


@pytest.mark.parametrize(
    ("factory", "end", "mods", "hint"),
    [
        (
            LineTool,
            QPointF(200, 100),
            NONE,
            "L: 100px ∠ 0.0° | Shift: snap to 15° | Release to confirm.",
        ),
        (
            ArrowTool,
            QPointF(200, 100),
            NONE,
            "L: 100px ∠ 0.0° | Shift: snap to 15° | Release to confirm.",
        ),
        (
            RectangleTool,
            QPointF(200, 160),
            NONE,
            "W: 100 H: 60 | Shift: square | Alt or Ctrl: from center | Release to confirm.",
        ),
        (
            EllipseTool,
            QPointF(200, 160),
            NONE,
            "W: 100 H: 60 | Shift: circle | Alt or Ctrl: from center | Release to confirm.",
        ),
        (
            EllipseTool,
            QPointF(200, 160),
            SHIFT,
            "D: 100 | Alt or Ctrl: from center | Release to confirm.",
        ),
        (
            FreehandTool,
            QPointF(200, 160),
            NONE,
            "Drawing… Shift: straight segments. Release to finish.",
        ),
    ],
)
def test_each_tool_shows_its_drawing_row(
    qtbot: QtBot,
    scene: SnapScene,
    factory: type[BaseTool],
    end: QPointF,
    mods: Qt.KeyboardModifier,
    hint: str,
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, end, mods)
    assert tool.status_hint == hint
    # The row's values are the tooltip's own
    assert hint.startswith(tool.drawing_measurement[0])


@pytest.mark.parametrize(
    ("factory", "idle"),
    [
        (LineTool, "Click and drag to draw a line. Shift: constrain angle."),
        (ArrowTool, "Click and drag to draw an arrow. Shift: constrain angle."),
        (
            RectangleTool,
            "Click and drag to draw a rectangle. Shift: square. Alt or Ctrl: from center.",
        ),
        (
            EllipseTool,
            "Click and drag to draw an ellipse. Shift: circle. Alt or Ctrl: from center.",
        ),
        (
            FreehandTool,
            "Click and drag to draw a freehand stroke. Shift: constrain to straight segments.",
        ),
    ],
)
def test_each_tool_returns_to_its_idle_row(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], idle: str
) -> None:
    """3.7 and 4.8's Idle rows are corrected here; 5.7, 6.7, and 9.11's were in Phase 2."""
    view, tool = _setup(qtbot, scene, factory)
    assert tool.status_hint == idle
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    assert tool.status_hint != idle
    _release(tool, view, QPointF(200, 160))
    assert tool.status_hint == idle


def test_the_status_bar_follows_the_drag_and_returns_to_idle(main_window: MainWindow) -> None:
    view = main_window.view
    main_window.tool_manager.activate("ellipse")
    tool = main_window.tool_manager.active_tool
    assert tool is not None
    label = main_window._status_bar._hint_label  # noqa: SLF001
    idle = tool.status_hint

    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(160, 120))
    assert (
        label.text()
        == "W: 100 H: 60 | Shift: circle | Alt or Ctrl: from center | Release to confirm."
    )
    _move(tool, view, QPointF(160, 120), SHIFT)
    assert label.text() == "D: 100 | Alt or Ctrl: from center | Release to confirm."

    _release(tool, view, QPointF(160, 120))
    assert main_window.tool_manager.active_tool_id != "ellipse" or label.text() == idle


def test_escape_puts_the_idle_row_back(main_window: MainWindow) -> None:
    view = main_window.view
    main_window.tool_manager.activate("line")
    tool = main_window.tool_manager.active_tool
    assert tool is not None
    label = main_window._status_bar._hint_label  # noqa: SLF001
    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(160, 60))
    assert label.text().startswith("L: 100px")
    assert tool.handle_escape()
    assert label.text() == "Click and drag to draw a line. Shift: constrain angle."


# --------------------------------------------------------------- the guide lines (decision 3)


class _RecordingPainter:
    """Stands in for a QPainter and keeps the lines drawn."""

    def __init__(self) -> None:
        self.lines: list[tuple[QPointF, QPointF]] = []
        self.pen: QPen | None = None

    def drawLine(self, a: QPointF, b: QPointF) -> None:  # noqa: N802
        self.lines.append((QPointF(a), QPointF(b)))

    def setPen(self, pen: QPen) -> None:  # noqa: N802
        self.pen = QPen(pen)

    def save(self) -> None: ...

    def restore(self) -> None: ...

    def setRenderHint(self, *_args: object) -> None: ...  # noqa: N802


def _guides_drawn(view: SnapView) -> _RecordingPainter:
    painter = _RecordingPainter()
    view._draw_drawing_guides(painter)  # type: ignore[arg-type]  # noqa: SLF001
    return painter


@pytest.mark.parametrize(
    ("factory", "edges"),
    [
        (RectangleTool, QRectF(100, 100, 100, 60)),
        (EllipseTool, QRectF(100, 100, 100, 60)),
        (LineTool, QRectF(100, 100, 100, 60)),
        (ArrowTool, QRectF(100, 100, 100, 60)),
    ],
)
def test_the_guides_start_from_the_shapes_own_edges(
    qtbot: QtBot, scene: SnapScene, factory: type[BaseTool], edges: QRectF
) -> None:
    """The stroke and the shadow are left out: the lines line up with the geometry."""
    view, tool = _setup(qtbot, scene, factory)
    tool.creation_defaults["stroke_width"] = 12.0
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    assert view.drawing_guides == edges


def test_the_guides_follow_the_modifiers(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _press(tool, view, QPointF(200, 200))
    _move(tool, view, QPointF(260, 220), SHIFT | CTRL)
    assert view.drawing_guides == QRectF(140, 140, 120, 120)


def test_the_guides_go_when_the_drag_ends(qtbot: QtBot, scene: SnapScene) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    for end in (tool.cancel, lambda: _release(tool, view, QPointF(200, 160))):
        _press(tool, view, QPointF(100, 100))
        _move(tool, view, QPointF(200, 160))
        assert view.drawing_guides is not None
        end()
        assert view.drawing_guides is None


def test_the_four_lines_run_to_the_two_rulers(qtbot: QtBot, scene: SnapScene) -> None:
    """The left and right edges run up to the horizontal ruler, the top and bottom edges
    left to the vertical ruler, dashed, in the accent colour at 30 percent."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    view.set_rulers_visible(True)
    _press(tool, view, QPointF(200, 200))
    _move(tool, view, QPointF(300, 260))
    origin = view.mapToScene(0, 0)

    drawn = _guides_drawn(view)
    assert sorted((a.x(), a.y(), b.x(), b.y()) for a, b in drawn.lines) == sorted(
        [
            (200, 200, 200, origin.y()),
            (300, 200, 300, origin.y()),
            (200, 200, origin.x(), 200),
            (200, 260, origin.x(), 260),
        ]
    )
    assert drawn.pen is not None
    assert drawn.pen.style() == Qt.PenStyle.DashLine
    assert drawn.pen.isCosmetic() and drawn.pen.widthF() == 0
    assert drawn.pen.color().alphaF() == pytest.approx(0.3, abs=0.01)


def test_a_shape_off_the_top_draws_no_line_to_the_horizontal_ruler(
    qtbot: QtBot, scene: SnapScene
) -> None:
    """A line runs from an edge to its ruler only where the edge is on the ruler's inner
    side of the viewport; a shape past the top has no vertical line to draw."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    view.set_rulers_visible(True)
    origin = view.mapToScene(0, 0)
    _press(tool, view, QPointF(200, origin.y() - 40))
    _move(tool, view, QPointF(300, origin.y() + 60))
    drawn = _guides_drawn(view)
    assert all(a.y() == b.y() for a, b in drawn.lines)  # horizontal lines only
    assert len(drawn.lines) == 2  # noqa: PLR2004


def _grab(view: SnapView) -> QImage:
    viewport = view.viewport()
    assert viewport is not None
    return viewport.grab().toImage()


def test_the_guides_are_painted_only_while_the_rulers_are_visible(
    qtbot: QtBot, scene: SnapScene, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    calls: list[int] = []
    original = view._draw_drawing_guides  # noqa: SLF001

    def _record(painter: QPainter) -> None:
        calls.append(1)
        original(painter)

    monkeypatch.setattr(view, "_draw_drawing_guides", _record)
    _press(tool, view, QPointF(200, 200))
    _move(tool, view, QPointF(300, 260))
    _grab(view)
    assert calls == []

    view.set_rulers_visible(True)
    _move(tool, view, QPointF(301, 261))
    _grab(view)
    assert calls


def test_the_lines_reach_the_screen(qtbot: QtBot, scene: SnapScene) -> None:
    """Over the white canvas above the shape, the column of its left edge carries the
    dashed line; the same column without a drag does not."""
    scene.set_background_color(QColor("#FFFFFF"))
    view, tool = _setup(qtbot, scene, RectangleTool)
    view.set_rulers_visible(True)
    _press(tool, view, QPointF(200, 200))
    _move(tool, view, QPointF(300, 260))
    left = view.mapFromScene(QPointF(200, 200))
    top = view.mapFromScene(QPointF(200, 20))

    def _column(image: QImage) -> list[QColor]:
        return [image.pixelColor(left.x(), y) for y in range(top.y(), left.y() - 4)]

    with_guides = _column(_grab(view))
    view.set_drawing_guides(None)
    without = _column(_grab(view))
    assert with_guides != without
    assert all(c == QColor("#FFFFFF") for c in without)


def test_the_guides_never_reach_a_render_of_the_scene(qtbot: QtBot, scene: SnapScene) -> None:
    from snapmock.core.render_engine import RenderEngine

    scene.set_background_color(QColor("#FFFFFF"))
    view, tool = _setup(qtbot, scene, RectangleTool)
    view.set_rulers_visible(True)
    _press(tool, view, QPointF(200, 200))
    _move(tool, view, QPointF(300, 260))
    export = RenderEngine(scene).render_to_image()
    assert all(export.pixelColor(200, y) == QColor("#FFFFFF") for y in range(10, 190))


def test_the_arc_and_the_polygon_draw_guides_from_their_own_edges(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view, arc = _setup(qtbot, scene, ArcTool)
    _press(arc, view, QPointF(100, 200))
    _move(arc, view, QPointF(300, 200))
    _release(arc, view, QPointF(300, 200))
    _move(arc, view, QPointF(200, 120), buttons=NO_BUTTON)
    guides = view.drawing_guides
    assert guides is not None
    assert guides.left() == pytest.approx(100) and guides.right() == pytest.approx(300)
    assert guides.top() == pytest.approx(120, abs=0.5) and guides.bottom() == pytest.approx(200)
    arc.cancel()
    assert view.drawing_guides is None

    polygon = PolygonTool()
    polygon.activate(scene, SelectionManager(scene))
    for pos in (QPointF(100, 100), QPointF(200, 100)):
        _press(polygon, view, pos)
        _release(polygon, view, pos)
    _move(polygon, view, QPointF(200, 180), buttons=NO_BUTTON)
    assert view.drawing_guides == QRectF(100, 100, 100, 80)


# --------------------------------------------------------------- the cost per move


def test_the_guides_and_the_hint_cost_little_per_move(qtbot: QtBot, scene: SnapScene) -> None:
    """Section 12's 60 frames a second; the measured figure is in the notes."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    view.set_rulers_visible(True)
    _press(tool, view, QPointF(100, 100))
    events = [
        _mouse(view, QEvent.Type.MouseMove, QPointF(150 + i, 150 + (i % 30))) for i in range(200)
    ]
    start = time.perf_counter()
    for event in events:
        tool.mouse_move(event)
        QApplication.processEvents()
    per_move_ms = (time.perf_counter() - start) * 1000.0 / len(events)
    assert per_move_ms < 16.7  # noqa: PLR2004
