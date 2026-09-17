"""The canvas's own resize handles, and a crop that cuts the image (end-to-end pass
findings 13 and 14)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from snapmock.commands.layer_commands import CreateBackgroundLayerCommand
from snapmock.commands.raster_commands import CropCanvasCommand
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.main_window import MainWindow


def _capture(window: MainWindow, width: int = 300, height: int = 200) -> RasterRegionItem:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("green"))
    command = CreateBackgroundLayerCommand(window.scene, pixmap)
    window.scene.command_stack.push(command)
    return command.item


def _size(window: MainWindow) -> tuple[float, float]:
    size = window.scene.canvas_size
    return size.width(), size.height()


# ---- finding 14: a crop cuts the image at the new edge ----


def test_a_crop_cuts_the_image_and_undo_restores_it(main_window: MainWindow) -> None:
    """Navigation PRD 7.6: raster items are pixel-clipped to the crop boundary. The image
    was only moved, so its cut-away part hung over the pasteboard."""
    image = _capture(main_window)
    stack = main_window.scene.command_stack
    stack.push(CropCanvasCommand(main_window.scene, QRectF(50, 20, 100, 120)))
    assert _size(main_window) == (100, 120)
    assert (image.pixmap.width(), image.pixmap.height()) == (100, 120)
    assert image.pos() == QPointF(0, 0)
    stack.undo()
    assert (image.pixmap.width(), image.pixmap.height()) == (300, 200)
    assert image.pos() == QPointF(0, 0)
    stack.redo()
    assert (image.pixmap.width(), image.pixmap.height()) == (100, 120)
    stack.mark_clean()


def test_a_crop_past_the_canvas_extends_it_and_leaves_the_image_whole(
    main_window: MainWindow,
) -> None:
    image = _capture(main_window)
    main_window.scene.command_stack.push(
        CropCanvasCommand(main_window.scene, QRectF(-20, -10, 340, 220))
    )
    assert _size(main_window) == (340, 220)
    assert image.pos() == QPointF(20, 10)
    assert (image.pixmap.width(), image.pixmap.height()) == (300, 200)
    main_window.scene.command_stack.mark_clean()


# ---- finding 13: the crop tool's handles look like every other handle ----


def test_crop_handles_match_the_selection_handles() -> None:
    from snapmock.core.theme_manager import current_theme
    from snapmock.ui.crop_overlay import CropHandleItem
    from snapmock.ui.transform_handles import HandleItem, HandlePosition

    crop = CropHandleItem("top_left")
    item = HandleItem(HandlePosition.TOP_LEFT)
    assert crop.rect() == item.rect()
    assert crop.brush().color() == QColor(255, 255, 255)
    assert crop.pen().color() == current_theme().selection_handle
    assert crop.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    assert CropHandleItem("middle_right").cursor().shape() == Qt.CursorShape.SizeHorCursor


# ---- finding 13: the Select tool's canvas handles ----


@pytest.fixture()
def canvas_window(main_window: MainWindow) -> MainWindow:
    main_window.resize(1200, 800)
    main_window.show()
    _capture(main_window)
    main_window.tool_manager.activate("select")
    main_window.selection_manager.deselect_all()
    main_window.view.set_zoom(100)
    main_window.view.centerOn(150, 100)
    yield main_window
    main_window.scene.command_stack.mark_clean()


def _send(
    window: MainWindow,
    kind: QEvent.Type,
    x: float,
    y: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    view = window.view
    viewport = view.viewport()
    assert viewport is not None
    point = QPointF(view.mapFromScene(QPointF(x, y)))
    button = Qt.MouseButton.LeftButton
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
    event = QMouseEvent(
        kind, point, QPointF(viewport.mapToGlobal(point.toPoint())), button, buttons, modifiers
    )
    QApplication.sendEvent(viewport, event)


def _drag(
    window: MainWindow,
    start: tuple[float, float],
    end: tuple[float, float],
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    *,
    release: bool = True,
) -> None:
    _send(window, QEvent.Type.MouseButtonPress, *start)
    for step in range(1, 6):
        x = start[0] + (end[0] - start[0]) * step / 5
        y = start[1] + (end[1] - start[1]) * step / 5
        _send(window, QEvent.Type.MouseMove, x, y, modifiers)
    if release:
        _send(window, QEvent.Type.MouseButtonRelease, *end, modifiers)


def _near(actual: tuple[float, float], expected: tuple[float, float]) -> bool:
    return all(abs(a - e) <= 1 for a, e in zip(actual, expected, strict=True))


def test_the_canvas_shows_handles_while_nothing_is_selected(canvas_window: MainWindow) -> None:
    from snapmock.tools.select_tool import SelectTool
    from snapmock.ui.transform_handles import HandlePosition

    tool = canvas_window.tool_manager.active_tool
    assert isinstance(tool, SelectTool)
    handles = tool.canvas_handles
    assert handles is not None and handles.scene() is not None
    assert handles.current_rect == QRectF(0, 0, 300, 200)
    assert handles.handle_at(QPointF(300, 200)) is HandlePosition.BOTTOM_RIGHT
    assert handles.handle_at(QPointF(150, 0)) is HandlePosition.TOP_CENTER
    tool._update_hover_cursor(QPointF(300, 100))  # noqa: SLF001
    viewport = canvas_window.view.viewport()
    assert viewport is not None
    assert viewport.cursor().shape() == Qt.CursorShape.SizeHorCursor
    from snapmock.commands.add_item import AddItemCommand
    from snapmock.items.rectangle_item import RectangleItem

    layer = canvas_window.scene.layer_manager.active_layer
    assert layer is not None
    rect = RectangleItem(rect=QRectF(0, 0, 20, 20))
    rect.setPos(40, 40)
    canvas_window.scene.command_stack.push(
        AddItemCommand(canvas_window.scene, rect, layer.layer_id)
    )
    canvas_window.selection_manager.select(rect)
    assert handles.scene() is None  # an item's handles replace the canvas's
    canvas_window.selection_manager.deselect_all()
    assert handles.scene() is not None


def test_dragging_a_canvas_handle_inward_crops_the_image(canvas_window: MainWindow) -> None:
    window = canvas_window
    image = window.scene.annotation_items()[0]
    assert isinstance(image, RasterRegionItem)
    _drag(window, (300, 200), (250, 150))
    assert _near(_size(window), (250, 150))
    assert _near((image.pixmap.width(), image.pixmap.height()), (250, 150))
    assert window.scene.command_stack.undo_text == "Crop canvas"
    window.scene.command_stack.undo()
    assert _size(window) == (300, 200)
    _drag(window, (0, 100), (40, 100))  # the left edge: the image's left part goes
    assert _near(_size(window), (260, 200))
    assert _near((image.pos().x(), image.pos().y()), (0, 0))
    assert _near((image.pixmap.width(), image.pixmap.height()), (260, 200))


def test_dragging_a_canvas_handle_outward_extends_the_canvas(canvas_window: MainWindow) -> None:
    window = canvas_window
    image = window.scene.annotation_items()[0]
    assert isinstance(image, RasterRegionItem)
    _drag(window, (300, 200), (350, 260))
    assert _near(_size(window), (350, 260))
    assert (image.pixmap.width(), image.pixmap.height()) == (300, 200)  # not scaled
    assert image.pos() == QPointF(0, 0)
    window.scene.command_stack.undo()
    _drag(window, (0, 0), (-30, -20))
    assert _near(_size(window), (330, 220))
    assert _near((image.pos().x(), image.pos().y()), (30, 20))


def test_shift_keeps_the_canvas_proportions(canvas_window: MainWindow) -> None:
    window = canvas_window
    shift = Qt.KeyboardModifier.ShiftModifier
    _drag(window, (300, 200), (450, 210), shift)  # corner: the larger change wins
    assert _near(_size(window), (450, 300))
    window.scene.command_stack.undo()
    _drag(window, (300, 100), (240, 100), shift)  # edge: the other side follows, centred
    assert _near(_size(window), (240, 160))
    image = window.scene.annotation_items()[0]
    assert isinstance(image, RasterRegionItem)
    assert _near((image.pixmap.width(), image.pixmap.height()), (240, 160))


def test_escape_cancels_a_canvas_resize(canvas_window: MainWindow) -> None:
    from PyQt6.QtTest import QTest

    window = canvas_window
    _drag(window, (300, 200), (250, 150), release=False)
    window.view.setFocus()
    QTest.keyClick(window.view, Qt.Key.Key_Escape)
    _send(window, QEvent.Type.MouseButtonRelease, 250, 150)
    assert _size(window) == (300, 200)
    assert window.scene.command_stack.undo_text != "Crop canvas"
