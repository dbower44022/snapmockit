"""Tests for raster operations: crop, raster select, and select tool interactions."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.tools.crop_tool import CropTool
from snapmock.tools.raster_select_tool import RasterSelectTool
from snapmock.tools.select_tool import SelectTool
from snapmock.tools.tool_manager import ToolManager


def _make_mouse_event(
    event_type: QMouseEvent.Type,
    pos: QPoint,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    buttons: Qt.MouseButton = Qt.MouseButton.LeftButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    """Create a QMouseEvent for testing."""
    return QMouseEvent(
        event_type,
        QPointF(pos),
        QPointF(pos),  # globalPos
        button,
        buttons,
        modifiers,
    )


def _setup_scene_with_view_and_image() -> tuple[
    SnapScene, SnapView, SelectionManager, ToolManager
]:
    """Create a scene with a view and import a test image."""
    scene = SnapScene(width=800, height=600)
    view = SnapView(scene)
    view.resize(800, 600)
    view.show()
    QApplication.processEvents()

    sm = SelectionManager(scene)
    tm = ToolManager(scene, sm)
    view.set_tool_manager(tm)

    # Add a test image (200x150 red pixmap) at (100, 50)
    pixmap = QPixmap(200, 150)
    pixmap.fill(Qt.GlobalColor.red)
    item = RasterRegionItem(pixmap=pixmap)
    item.setPos(100, 50)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    cmd = AddItemCommand(scene, item, layer.layer_id)
    scene.command_stack.push(cmd)

    return scene, view, sm, tm


# --- View <-> ToolManager wiring ---


def test_view_routes_mouse_to_tool_manager(qtbot: object) -> None:
    """SnapView should delegate mouse events to the tool manager."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = RasterSelectTool()
    tm.register(tool)
    tm.activate("raster_select")

    assert tool._scene is not None
    assert tool._view is view

    # Simulate mouse press at viewport center
    center = QPoint(400, 300)
    event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, center)
    view.mousePressEvent(event)
    assert tool._state.name == "DRAWING", f"Expected DRAWING, got {tool._state.name}"

    view.close()


# --- Raster Select Tool ---


def test_raster_select_draw_selection(qtbot: object) -> None:
    """Drawing a selection rectangle should transition through states correctly."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = RasterSelectTool()
    tm.register(tool)
    tm.activate("raster_select")

    # Press at (150, 100)
    press_pos = QPoint(150, 100)
    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, press_pos)
    view.mousePressEvent(press_event)
    assert tool._state.name == "DRAWING"
    assert tool._overlay is not None

    # Move to (350, 250)
    move_pos = QPoint(350, 250)
    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        move_pos,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)
    assert tool._state.name == "DRAWING"

    # Release
    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, move_pos)
    view.mouseReleaseEvent(release_event)
    # Should be ACTIVE if the rect is large enough
    assert tool._state.name == "ACTIVE", f"Expected ACTIVE, got {tool._state.name}"

    # Overlay should have a non-trivial selection rect
    rect = tool.selection_rect
    assert rect.width() > 0, f"Selection width = {rect.width()}"
    assert rect.height() > 0, f"Selection height = {rect.height()}"

    view.close()


def test_raster_select_move_marquee(qtbot: object) -> None:
    """Clicking inside an active raster selection should move it."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = RasterSelectTool()
    tm.register(tool)
    tm.activate("raster_select")

    # Draw a selection
    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, QPoint(100, 100))
    view.mousePressEvent(press_event)
    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        QPoint(300, 250),
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)
    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, QPoint(300, 250))
    view.mouseReleaseEvent(release_event)
    assert tool._state.name == "ACTIVE"

    # Now click inside and drag to move
    inside_pt = QPoint(200, 175)
    press_event2 = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, inside_pt)
    view.mousePressEvent(press_event2)
    assert tool._state.name == "MOVING", f"Expected MOVING, got {tool._state.name}"

    view.close()


def test_raster_select_cancel(qtbot: object) -> None:
    """Pressing Escape should cancel the raster selection."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = RasterSelectTool()
    tm.register(tool)
    tm.activate("raster_select")

    # Draw a selection
    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, QPoint(100, 100))
    view.mousePressEvent(press_event)
    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        QPoint(300, 250),
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)
    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, QPoint(300, 250))
    view.mouseReleaseEvent(release_event)
    assert tool._state.name == "ACTIVE"

    # Cancel
    from PyQt6.QtGui import QKeyEvent

    esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    result = tool.key_press(esc)
    assert result is True
    assert tool._state.name == "IDLE"
    assert tool._overlay is None

    view.close()


# --- Crop Tool ---


def test_crop_tool_initial_state(qtbot: object) -> None:
    """Crop tool should start in ADJUSTING state with full-canvas overlay."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = CropTool()
    tm.register(tool)
    tm.activate("crop")

    assert tool._state.name == "ADJUSTING"
    assert tool._overlay is not None
    crop_rect = tool._overlay.crop_rect
    # Should match canvas size
    assert crop_rect.width() == 800, f"Crop width = {crop_rect.width()}"
    assert crop_rect.height() == 600, f"Crop height = {crop_rect.height()}"

    view.close()


def test_crop_tool_handle_hit(qtbot: object) -> None:
    """Clicking on a crop handle should transition to RESIZING."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = CropTool()
    tm.register(tool)
    tm.activate("crop")

    assert tool._overlay is not None

    # The bottom_right handle is at (800, 600) in scene coords.
    # We need to convert scene->viewport to simulate the mouse event.
    scene_pt = QPointF(800, 600)
    viewport_pt = view.mapFromScene(scene_pt)

    # Check if the handle is actually at that position
    handle_name = tool._overlay.handle_at(scene_pt)
    assert handle_name is not None, (
        f"No handle at scene pos (800, 600). "
        f"Handle rects: {[(n, h.sceneBoundingRect()) for n, h in tool._overlay._handles.items()]}"
    )

    # Simulate mouse press at the handle position
    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, viewport_pt)
    view.mousePressEvent(press_event)
    assert tool._state.name == "RESIZING", f"Expected RESIZING, got {tool._state.name}"

    view.close()


def test_crop_tool_interior_move(qtbot: object) -> None:
    """Clicking inside the crop rect should transition to MOVING."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = CropTool()
    tm.register(tool)
    tm.activate("crop")

    assert tool._overlay is not None

    # Click at center of canvas (400, 300) — should be inside the crop rect
    center_scene = QPointF(400, 300)
    center_viewport = view.mapFromScene(center_scene)

    # Verify the point is inside the crop rect
    assert tool._overlay.is_inside_crop(center_scene), "Center should be inside crop rect"

    # Verify no handle at center
    handle = tool._overlay.handle_at(center_scene)
    assert handle is None, f"Unexpected handle at center: {handle}"

    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, center_viewport)
    view.mousePressEvent(press_event)
    assert tool._state.name == "MOVING", f"Expected MOVING, got {tool._state.name}"

    # Move the crop rect
    new_pos = QPoint(center_viewport.x() + 50, center_viewport.y() + 30)
    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        new_pos,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)
    assert tool._state.name == "MOVING"

    # Release
    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, new_pos)
    view.mouseReleaseEvent(release_event)
    assert tool._state.name == "ADJUSTING"

    # Crop rect should have moved
    new_crop_rect = tool._overlay.crop_rect
    assert new_crop_rect.topLeft() != QPointF(0, 0), f"Crop rect didn't move: {new_crop_rect}"

    view.close()


def test_crop_tool_resize_handle(qtbot: object) -> None:
    """Dragging a crop handle should resize the crop rect."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = CropTool()
    tm.register(tool)
    tm.activate("crop")

    assert tool._overlay is not None
    original_rect = tool._overlay.crop_rect

    # Click on the middle_right handle (at scene x=800, y=300)
    handle_scene = QPointF(800, 300)
    handle_viewport = view.mapFromScene(handle_scene)

    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, handle_viewport)
    view.mousePressEvent(press_event)
    assert tool._state.name == "RESIZING", f"Expected RESIZING, got {tool._state.name}"

    # Drag left by 100 pixels
    new_scene = QPointF(700, 300)
    new_viewport = view.mapFromScene(new_scene)
    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        new_viewport,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)

    # Release
    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, new_viewport)
    view.mouseReleaseEvent(release_event)
    assert tool._state.name == "ADJUSTING"

    # The crop rect should now be narrower
    new_rect = tool._overlay.crop_rect
    assert new_rect.width() < original_rect.width(), (
        f"Expected width < {original_rect.width()}, got {new_rect.width()}"
    )

    view.close()


# --- Select Tool (with imported raster item) ---


def test_select_tool_click_item(qtbot: object) -> None:
    """Clicking on an imported image item should select it."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = SelectTool()
    tm.register(tool)
    tm.activate("select")

    # The raster item is at (100, 50), size 200x150
    # Click at (200, 125) which is inside the item
    click_scene = QPointF(200, 125)
    click_viewport = view.mapFromScene(click_scene)

    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, click_viewport)
    view.mousePressEvent(press_event)

    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, click_viewport)
    view.mouseReleaseEvent(release_event)

    # Item should be selected
    assert sm.count > 0, f"Expected item to be selected, but selection count = {sm.count}"

    view.close()


def test_select_tool_rubber_band(qtbot: object) -> None:
    """Rubber-band selection should select items within the rect."""
    scene, view, sm, tm = _setup_scene_with_view_and_image()

    tool = SelectTool()
    tm.register(tool)
    tm.activate("select")

    # Rubber-band from (50, 20) to (350, 250), which should encompass the item at (100,50) 200x150
    start_viewport = view.mapFromScene(QPointF(50, 20))
    end_viewport = view.mapFromScene(QPointF(350, 250))

    press_event = _make_mouse_event(QMouseEvent.Type.MouseButtonPress, start_viewport)
    view.mousePressEvent(press_event)

    move_event = _make_mouse_event(
        QMouseEvent.Type.MouseMove,
        end_viewport,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    view.mouseMoveEvent(move_event)

    release_event = _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, end_viewport)
    view.mouseReleaseEvent(release_event)

    assert sm.count > 0, f"Expected item to be selected via rubber-band, count = {sm.count}"

    view.close()


def test_raster_selection_size_readout_is_the_overlay_not_a_tooltip(qtbot: object) -> None:
    """The W / H readout while a raster selection is drawn is the widget over the viewport,
    never a Qt tooltip window (end-to-end pass finding 3, with the Select tool's move)."""
    from PyQt6.QtWidgets import QToolTip

    from snapmock.ui.dimension_overlay import existing_dimension_overlay

    scene, view, sm, tm = _setup_scene_with_view_and_image()
    tool = RasterSelectTool()
    tm.register(tool)
    tm.activate("raster_select")
    viewport = view.viewport()
    assert viewport is not None

    view.mousePressEvent(_make_mouse_event(QMouseEvent.Type.MouseButtonPress, QPoint(100, 100)))
    view.mouseMoveEvent(_make_mouse_event(QMouseEvent.Type.MouseMove, QPoint(180, 150)))
    overlay = existing_dimension_overlay(viewport)
    assert overlay is not None and not overlay.isHidden()
    assert overlay.text.startswith("W: ") and "H: " in overlay.text
    assert not QToolTip.isVisible()
    view.mouseReleaseEvent(
        _make_mouse_event(QMouseEvent.Type.MouseButtonRelease, QPoint(180, 150))
    )
    assert overlay.isHidden()
    assert tool._state.name == "ACTIVE"
    view.close()
