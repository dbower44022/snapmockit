"""The Freehand pipeline (Basic Shape PRD 9.3, 9.6, 9.7, 9.8, 9.9, 10.7; Basic Shape
remainder decision 2 and Phase 2 step 2)."""

from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import StrokeCap
from snapmock.core.path_utils import fit_cubic_beziers
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.items.freehand_item import FreehandItem
from snapmock.main_window import MainWindow
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.ui.property_panel import PropertyPanel

CLOSED_BAR = [
    "stroke_color",
    "fill_color",
    "stroke_width",
    "stroke_style",
    "fill_opacity",
    "stroke_opacity",
    "shadow_enabled",
    "smoothing",
]


def _wavy(count: int = 300) -> list[QPointF]:
    """A hand-drawn wave: a sine with a pixel of jitter on every other sample."""
    return [QPointF(i, 30 * math.sin(i / 25.0) + (i % 2) * 0.8) for i in range(count)]


def _item(points: list[QPointF]) -> FreehandItem:
    item = FreehandItem()
    for p in points:
        item.add_point(p)
    return item


def _circle(radius: float = 50.0, count: int = 90) -> list[QPointF]:
    return [
        QPointF(
            60 + radius * math.cos(2 * math.pi * k / count),
            60 + radius * math.sin(2 * math.pi * k / count),
        )
        for k in range(count)
    ]


def _render(item: FreehandItem) -> QImage:
    image = QImage(160, 160, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    item.paint(painter, None)
    painter.end()
    return image


def test_the_fitted_path_has_fewer_segments_as_smoothing_rises(qapp: QApplication) -> None:
    item = _item(_wavy())
    counts = [len(item.fit_segments(s)) for s in (0.0, 0.3, 1.0)]
    # The wave's 0.8 px of alternating jitter is noise the fit no longer chases: 0 and 30
    # percent share the noise floor of 1.5 px (Freehand remainder decision 2, option B),
    # so the count does not fall between them; it falls on a smooth stroke, below
    assert counts[0] >= counts[1] >= counts[2] >= 1
    assert item.fit_error(0.0) == item.fit_error(0.3) == 1.5
    circle = _item(_circle())
    smooth_counts = [len(circle.fit_segments(s)) for s in (0.0, 0.3, 1.0)]
    assert smooth_counts[0] > smooth_counts[1] >= smooth_counts[2] >= 1
    assert circle.fit_error(0.0) == 0.5  # no noise, no floor
    item.smooth(0.5)
    segments = item.bezier_segments
    assert segments[0][0] == item.path_points[0]
    assert segments[-1][3] == item.path_points[-1]
    # Every raw point lies within the two stages' tolerances of the painted curve
    path = item.path
    samples = [path.pointAtPercent(k / 600) for k in range(601)]
    reach = 0.5 * 5.0 + 0.5 * 3.0 + 1.5
    for raw in item.path_points:
        nearest = min(math.hypot(s.x() - raw.x(), s.y() - raw.y()) for s in samples)
        assert nearest <= reach


def test_resmoothing_starts_again_from_the_raw_points(qapp: QApplication) -> None:
    item = _item(_wavy())
    raw = item.path_points
    item.smooth(0.9)
    smooth = len(item.bezier_segments)
    item.smooth(0.0)
    assert len(item.bezier_segments) > smooth
    assert item.path_points == raw  # non-destructive (9.7)
    assert item.smoothing == 0.0


def test_the_fit_handles_short_and_straight_input() -> None:
    assert fit_cubic_beziers([], 1.0) == []
    one = fit_cubic_beziers([QPointF(3, 4)], 1.0)
    assert len(one) == 1 and one[0][0] == QPointF(3, 4)
    line = fit_cubic_beziers([QPointF(0, 0), QPointF(50, 0), QPointF(100, 0)], 0.5)
    assert len(line) == 1 and line[0][3] == QPointF(100, 0)
    # A long stroke with no noise at all never recurses out of the stack
    many = [QPointF(i, (i * i) % 7) for i in range(5000)]
    assert fit_cubic_beziers(many, 0.5)


def test_a_closed_stroke_fills_and_hits_inside(qapp: QApplication) -> None:
    item = _item(_circle())
    item.fill_color = QColor("#000000")
    item.smooth(0.5)
    centre = QPointF(60, 60)
    assert not item.shape().contains(centre)
    assert _render(item).pixelColor(60, 60).name() == "#ffffff"
    item.is_closed = True
    assert item.shape().contains(centre)
    assert _render(item).pixelColor(60, 60).name() == "#000000"
    item.fill_color = QColor(0, 0, 0, 0)
    assert not item.shape().contains(centre)  # a transparent fill is not clickable (9.9)


def test_the_hit_band_is_at_least_8_px(qapp: QApplication) -> None:
    item = _item([QPointF(x, 0) for x in range(0, 101, 5)])
    item.stroke_width = 1.0
    item.smooth(0.5)
    assert item.shape().contains(QPointF(50, 3.5))
    assert not item.shape().contains(QPointF(50, 6.0))
    item.stroke_width = 10.0
    assert item.shape().contains(QPointF(50, 6.5))  # stroke width plus 4


def test_the_keys_round_trip_and_an_old_file_is_fitted_on_load(qapp: QApplication) -> None:
    item = _item(_wavy(60))
    item.is_closed = True
    item.smooth(0.3)
    data = item.serialize()
    assert data["path_points"][1] == {"x": 1.0, "y": 30 * math.sin(1 / 25.0) + 0.8}
    assert set(data["bezier_segments"][0]) == {"start", "cp1", "cp2", "end"}
    assert (data["smoothing"], data["is_closed"], data["pressure_data"]) == (0.3, True, None)
    restored = FreehandItem.deserialize(data)
    assert restored.bezier_segments == item.bezier_segments
    assert restored.path_points == item.path_points
    assert restored.is_closed and restored.smoothing == 0.3
    old = FreehandItem.deserialize(
        {"type": "FreehandItem", "points": [[0, 0], [50, 10], [100, 0]]}
    )
    assert len(old.path_points) == 3 and old.smoothing == 0.5
    assert old.bezier_segments and old.bezier_segments[-1][3] == QPointF(100, 0)
    assert not old.is_closed


def _event(kind: QEvent.Type, window: MainWindow, scene_pos: QPointF) -> QMouseEvent:
    vp = QPointF(window.view.mapFromScene(scene_pos))
    button = Qt.MouseButton.LeftButton
    return QMouseEvent(kind, vp, button, button, Qt.KeyboardModifier.NoModifier)


def test_the_bar_caps_and_close_path_reach_the_next_stroke(main_window: MainWindow) -> None:
    bar = main_window._tool_options  # noqa: SLF001
    tm = main_window.tool_manager
    tm.activate("freehand")
    tool = tm.active_tool
    assert isinstance(tool, FreehandTool)
    assert list(bar.shared_widgets) == CLOSED_BAR
    caps = tool.cap_buttons
    assert list(caps) == [StrokeCap.FLAT, StrokeCap.ROUND, StrokeCap.SQUARE]
    assert caps[StrokeCap.ROUND].isChecked()
    close = tool.close_path_button
    assert close is not None and close.accessibleName() == "Close path"
    caps[StrokeCap.SQUARE].click()
    close.click()
    assert tool.creation_defaults["stroke_cap"] is StrokeCap.SQUARE
    assert tool.creation_defaults["close_path"] is True
    tm.handle_mouse_press(_event(QEvent.Type.MouseButtonPress, main_window, QPointF(40, 40)))
    for p in _circle(40, 36)[1:]:
        tm.handle_mouse_move(_event(QEvent.Type.MouseMove, main_window, p))
    tm.handle_mouse_release(_event(QEvent.Type.MouseButtonRelease, main_window, QPointF(99, 60)))
    items = [i for i in main_window.scene.annotation_items() if isinstance(i, FreehandItem)]
    assert len(items) == 1
    stroke = items[0]
    assert stroke.is_closed and stroke.stroke_cap is StrokeCap.SQUARE
    assert stroke.smoothing == 0.5 and stroke.bezier_segments


def test_an_accidental_click_draws_nothing(main_window: MainWindow) -> None:
    tm = main_window.tool_manager
    tm.activate("freehand")
    tm.handle_mouse_press(_event(QEvent.Type.MouseButtonPress, main_window, QPointF(40, 40)))
    tm.handle_mouse_move(_event(QEvent.Type.MouseMove, main_window, QPointF(41, 40)))
    tm.handle_mouse_release(_event(QEvent.Type.MouseButtonRelease, main_window, QPointF(41, 40)))
    assert not main_window.scene.annotation_items()
    tm.activate("freehand")
    tm.handle_mouse_press(_event(QEvent.Type.MouseButtonPress, main_window, QPointF(40, 40)))
    tm.handle_mouse_move(_event(QEvent.Type.MouseMove, main_window, QPointF(90, 40)))
    tm.handle_mouse_release(_event(QEvent.Type.MouseButtonRelease, main_window, QPointF(90, 40)))
    assert len(main_window.scene.annotation_items()) == 1  # a straight underline is kept


def test_the_panel_resmooths_a_selected_stroke(qtbot: QtBot) -> None:
    scene = SnapScene()
    sm = SelectionManager(scene)
    panel = PropertyPanel(sm, scene)
    qtbot.addWidget(panel)
    panel.show()
    item = _item(_wavy())
    item.smooth(0.5)
    before = item.bezier_segments
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    sm.select(item)
    assert panel._freehand_section.isVisible()  # noqa: SLF001
    spin = panel._freehand_smoothing_spin  # noqa: SLF001
    assert spin.value() == 50
    spin.setValue(95)
    assert item.smoothing == 0.95
    assert len(item.bezier_segments) < len(before)
    assert scene.command_stack.undo_text == "Change smoothing_fit"
    scene.command_stack.undo()
    assert item.smoothing == 0.5 and item.bezier_segments == before
    check = panel._freehand_closed_check  # noqa: SLF001
    check.setChecked(True)
    assert item.is_closed
    scene.command_stack.undo()
    assert not item.is_closed
