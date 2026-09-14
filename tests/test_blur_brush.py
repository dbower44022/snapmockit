"""The Blur tool's freeform brush (Blur PRD 2.3, 2.6, 2.11).

Press and drag paints into the region's alpha mask; strokes accumulate into one region,
Enter or a tool switch finalizes it, Escape drops it, and a region with nothing painted is
dropped too. Freeform blur decision 1, option A.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import (
    BLUR_BRUSH_SIZE_MAX,
    BLUR_BRUSH_SIZE_MIN,
    DEFAULT_BLUR_BRUSH_SIZE,
    BlurRegionShape,
)
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.blur_item import BlurItem
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.tools.blur_tool import BlurTool
from snapmock.ui.cursors import BRUSH_CURSOR_MAX, brush_cursor, reset_cursor_cache


def _stripes(width: int = 300, height: int = 200, band: int = 4) -> QPixmap:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    for x in range(0, width, band):
        painter.fillRect(
            x, 0, band, height, QColor("#000000") if (x // band) % 2 else QColor("#ffffff")
        )
    painter.end()
    return QPixmap.fromImage(image)


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    s = SnapScene(width=400, height=300)
    layer = s.layer_manager.active_layer
    assert layer is not None
    s.command_stack.push(AddItemCommand(s, RasterRegionItem(_stripes()), layer.layer_id))
    return s


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


def _brush_tool(scene: SnapScene) -> BlurTool:
    tool = BlurTool()
    tool.activate(scene, SelectionManager(scene))
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    return tool


def _stroke(
    tool: BlurTool,
    view: SnapView,
    points: list[QPointF],
    mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, points[0]))
    for point in points[1:]:
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, point, mods))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, points[-1], mods))


def _blurs(scene: SnapScene) -> list[BlurItem]:
    """The committed regions: one being painted is in the scene but on no layer yet."""
    return [i for i in scene.annotation_items() if isinstance(i, BlurItem) and i.layer_id]


def test_painting_makes_a_region_whose_rect_is_the_painted_bounds(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    tool = _brush_tool(scene)
    tool.creation_defaults["brush_size"] = 20.0
    _stroke(tool, view, [QPointF(100, 100), QPointF(160, 100)])
    item = tool.preview
    assert item is not None and item.region_shape is BlurRegionShape.FREEFORM
    # 20 px across the 100 to 160 stroke, plus the round caps and a pixel of antialiasing
    assert item.pos().x() == pytest.approx(89, abs=2) and item.pos().y() == pytest.approx(
        89, abs=2
    )
    assert item.rect.width() == pytest.approx(82, abs=4)
    assert item.rect.height() == pytest.approx(22, abs=4)
    mask = item.alpha_mask
    assert mask is not None
    middle = mask.pixelColor(int(130 - item.pos().x()), int(100 - item.pos().y()))
    corner = mask.pixelColor(0, 0)
    assert middle.alpha() == 255 and corner.alpha() == 0
    assert not _blurs(scene)  # nothing is committed until the region is finished


def test_several_strokes_accumulate_into_one_region(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    tool = _brush_tool(scene)
    tool.creation_defaults["brush_size"] = 20.0
    _stroke(tool, view, [QPointF(100, 100), QPointF(140, 100)])
    first = tool.preview
    assert first is not None
    width = first.rect.width()
    _stroke(tool, view, [QPointF(100, 200), QPointF(140, 200)])
    assert tool.preview is first  # the same region, painted into twice
    assert first.rect.height() > 110 and first.rect.width() == pytest.approx(width, abs=2)
    mask = first.alpha_mask
    assert mask is not None
    origin = first.pos()
    assert mask.pixelColor(int(120 - origin.x()), int(100 - origin.y())).alpha() == 255
    assert mask.pixelColor(int(120 - origin.x()), int(200 - origin.y())).alpha() == 255
    assert mask.pixelColor(int(120 - origin.x()), int(150 - origin.y())).alpha() == 0


def test_shift_holds_the_stroke_straight_from_the_press_point(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    tool = _brush_tool(scene)
    tool.creation_defaults["brush_size"] = 10.0
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(100, 100)))
    shift = Qt.KeyboardModifier.ShiftModifier
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(140, 160), shift))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, QPointF(180, 100), shift))
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(180, 100), shift))
    item = tool.preview
    assert item is not None
    mask = item.alpha_mask
    assert mask is not None
    origin = item.pos()
    # The straight line from the press point to the last position is painted
    assert mask.pixelColor(int(140 - origin.x()), int(100 - origin.y())).alpha() == 255
    # The path the cursor took on the way is gone: the region is a flat band, not a V
    assert item.rect.height() < 20 and item.rect.width() > 80
    assert item.pos().y() == pytest.approx(94, abs=2)


def test_enter_finishes_the_region_and_escape_drops_it(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    tool = _brush_tool(scene)
    _stroke(tool, view, [QPointF(100, 100), QPointF(150, 120)])
    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert tool.key_press(enter)
    placed = _blurs(scene)
    assert len(placed) == 1 and placed[0].region_shape is BlurRegionShape.FREEFORM
    assert placed[0].alpha_mask is not None
    assert not tool.painting

    _stroke(tool, view, [QPointF(200, 200), QPointF(250, 220)])
    assert tool.painting
    assert tool.handle_escape()
    assert len(_blurs(scene)) == 1  # the second region is gone
    assert not tool.painting and tool.preview is None


def test_a_tool_switch_finalizes_and_an_empty_region_is_dropped(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    tool = _brush_tool(scene)
    _stroke(tool, view, [QPointF(100, 100), QPointF(150, 120)])
    tool.cancel()  # the tool manager cancels the live stroke, then deactivates
    assert tool.painting  # the region survives a cancelled stroke
    tool.deactivate()
    assert len(_blurs(scene)) == 1

    tool.activate(scene, SelectionManager(scene))
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(100, 100)))
    assert tool.preview is not None
    tool.handle_escape()
    tool.deactivate()
    assert len(_blurs(scene)) == 1  # nothing new: the region was dropped


def test_the_hints_follow_the_shape_and_the_stroke(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    tool = BlurTool()
    tool.activate(scene, SelectionManager(scene))
    assert tool.status_hint.startswith("Click and drag to define blur region")
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    assert tool.status_hint == (
        "Paint to define blur area. Enter: finish. Shift: straight strokes."
    )
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, QPointF(100, 100)))
    assert tool.status_hint == ("Painting blur area. Release and continue, or Enter to finish.")
    tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(100, 100)))
    assert tool.status_hint.startswith("Paint to define blur area.")
    tool.handle_escape()


def test_the_brush_cursor_shows_the_brush_size(qtbot: QtBot, scene: SnapScene) -> None:
    reset_cursor_cache()
    view = _view(qtbot, scene)
    tool = BlurTool()
    tool.activate(scene, SelectionManager(scene))
    assert tool.cursor is Qt.CursorShape.CrossCursor
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    tool.creation_defaults["brush_size"] = 40.0
    cursor = tool.cursor
    assert not isinstance(cursor, Qt.CursorShape)
    assert cursor.pixmap().width() == 46 and cursor.hotSpot().x() == 23
    assert view.zoom_percent == 100
    tool.creation_defaults["brush_size"] = 200.0
    assert tool.cursor.pixmap().width() == BRUSH_CURSOR_MAX + 6  # a cursor cannot grow on
    assert brush_cursor(30).pixmap().width() == 36


def test_the_brush_cursor_follows_the_zoom(qtbot: QtBot, scene: SnapScene) -> None:
    """The circle is drawn in screen pixels, so a zoom re-draws it at the new size on the
    viewport without a tool switch or a bar change (found by the Freehand remainder work)."""
    reset_cursor_cache()
    view = _view(qtbot, scene)
    tool = BlurTool()
    tool.creation_defaults["region_shape"] = BlurRegionShape.FREEFORM
    tool.creation_defaults["brush_size"] = 20.0
    tool.activate(scene, SelectionManager(scene))
    viewport = view.viewport()
    assert viewport is not None
    assert viewport.cursor().pixmap().width() == 26
    view.set_zoom(400)
    assert viewport.cursor().pixmap().width() == 86
    view.set_zoom(50)
    assert viewport.cursor().pixmap().width() == 16
    tool.deactivate()
    view.set_zoom(200)  # disconnected: nothing raises and the cursor is not the tool's


def test_the_bar_shows_brush_size_only_for_a_freeform_region(main_window: object) -> None:
    tm = main_window.tool_manager  # type: ignore[attr-defined]
    tm.activate("blur")
    tool = tm.active_tool
    assert isinstance(tool, BlurTool)
    groups = tool.control_actions()

    def shown(name: str) -> bool:
        return all(a.isVisible() for a in groups[name])

    assert list(tool.shape_buttons) == [
        BlurRegionShape.RECTANGLE,
        BlurRegionShape.ELLIPSE,
        BlurRegionShape.FREEFORM,
        BlurRegionShape.WHOLE_LAYER,
    ]
    assert shown("corner") and not shown("brush")
    tool.shape_buttons[BlurRegionShape.FREEFORM].click()
    assert shown("brush") and not shown("corner")
    spin = tool.brush_spin
    assert spin is not None and spin.accessibleName() == "Brush Size"
    assert (spin.minimum(), spin.maximum()) == (BLUR_BRUSH_SIZE_MIN, BLUR_BRUSH_SIZE_MAX)
    assert spin.value() == DEFAULT_BLUR_BRUSH_SIZE
    spin.setValue(64)
    assert tool.brush_size == 64.0
