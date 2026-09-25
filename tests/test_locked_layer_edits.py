"""A locked layer refuses edits made through the Edit menu (end-to-end pass findings 10 and 11)."""

from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPixmap

from snapmock.commands.add_item import AddItemCommand
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.main_window import MainWindow
from snapmock.tools.raster_select_tool import RasterSelectTool, _RasterState


def _screenshot(window: MainWindow) -> RasterRegionItem:
    scene = window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    pixmap = QPixmap(200, 200)
    pixmap.fill(QColor("red"))
    item = RasterRegionItem(pixmap=pixmap)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def _raster_selection(window: MainWindow, rect: QRectF) -> RasterSelectTool:
    window.tool_manager.activate("raster_select")
    tool = window.tool_manager.active_tool
    assert isinstance(tool, RasterSelectTool)
    overlay = tool._ensure_overlay()  # noqa: SLF001
    overlay.set_selection_rect(rect)
    overlay.add_to_scene()
    tool._state = _RasterState.ACTIVE  # noqa: SLF001
    assert tool.has_active_selection
    return tool


def test_cut_of_a_raster_selection_on_a_locked_layer_is_refused(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """Navigation PRD 5.5.2 and 7: a lock prevents interactive editing. Edit > Cut erased
    the pixels of a locked layer's screenshot (end-to-end pass finding 10)."""
    item = _screenshot(main_window)
    layer = main_window.scene.layer_manager.active_layer
    assert layer is not None
    main_window.scene.layer_manager.set_locked(layer.layer_id, True)
    _raster_selection(main_window, QRectF(10, 10, 50, 50))
    main_window._edit_cut()  # noqa: SLF001
    assert unmet_messages
    assert "Cut needs an unlocked layer under the selection" in unmet_messages[-1][1]
    assert item._pixmap.toImage().pixelColor(30, 30).alpha() == 255  # noqa: SLF001
    assert main_window.scene.command_stack.undo_text != "Raster cut"
    main_window._edit_copy()  # noqa: SLF001
    assert main_window._clipboard.has_raster  # noqa: SLF001  (Copy still works)


def test_cut_of_a_raster_selection_on_an_unlocked_layer_still_erases(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    item = _screenshot(main_window)
    tool = _raster_selection(main_window, QRectF(10, 10, 50, 50))
    main_window._edit_cut()  # noqa: SLF001
    assert not unmet_messages
    assert item._pixmap.toImage().pixelColor(30, 30).alpha() == 0  # noqa: SLF001
    assert not tool.has_active_selection


# ---- the image on a Background layer stays in place (end-to-end pass finding 11) ----


def _background_image(window: MainWindow) -> RasterRegionItem:
    from snapmock.commands.layer_commands import CreateBackgroundLayerCommand

    pixmap = QPixmap(300, 200)
    pixmap.fill(QColor("blue"))
    command = CreateBackgroundLayerCommand(window.scene, pixmap)
    window.scene.command_stack.push(command)
    return command.item


def _click(window: MainWindow, x: float, y: float, dx: float = 0, dy: float = 0) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    view = window.view
    viewport = view.viewport()
    assert viewport is not None
    start = view.mapFromScene(x, y)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 6):
        QTest.mouseMove(viewport, start + QPoint(int(dx * step / 5), int(dy * step / 5)))
    end = start + QPoint(int(dx), int(dy))
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def test_the_background_image_cannot_be_selected_or_dragged(main_window: MainWindow) -> None:
    """Doug's decision A of 09-16-26: the image on a Background layer is fixed in place.
    After Flatten All the flattened image could be dragged about the canvas."""
    from PyQt6.QtCore import QPointF, Qt

    window = main_window
    window.resize(1200, 800)
    window.show()
    image = _background_image(window)
    window.tool_manager.activate("select")
    window.view.set_zoom(25)
    _click(window, 100, 100)
    assert window.selection_manager.is_empty
    _click(window, 100, 100, 60, 40)
    assert image.pos() == QPointF(0, 0)
    assert window.selection_manager.is_empty  # the rubber band passes over it too
    tool = window.tool_manager.active_tool
    assert tool is not None
    tool._update_hover_cursor(QPointF(100, 100))  # type: ignore[attr-defined]  # noqa: SLF001
    viewport = window.view.viewport()
    assert viewport is not None
    assert viewport.cursor().shape() == Qt.CursorShape.ForbiddenCursor


def test_no_route_selects_the_background_image(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    window = main_window
    image = _background_image(window)
    lm = window.scene.layer_manager
    background = lm.background_layer
    assert background is not None
    lm.set_active(background.layer_id)
    window._edit_select_all()  # noqa: SLF001
    assert window.selection_manager.is_empty
    # Since 09-24-26 (General UI PRD 2.55) Select All takes the whole canvas as a raster
    # selection instead of refusing; the image is still not selected as an item
    assert unmet_messages == []
    assert window.tool_manager.active_tool_id == "raster_select"
    window.tool_manager.activate("select")
    window._edit_select_all_layers()  # noqa: SLF001
    assert window.selection_manager.is_empty
    assert unmet_messages
    window.selection_manager.select(image)
    window.selection_manager.select_items([image])
    window.selection_manager.toggle(image)
    assert window.selection_manager.is_empty
    window.tool_manager.activate("select")
    tool = window.tool_manager.active_tool
    assert not tool.cycle_selection()  # type: ignore[union-attr]
    assert window.selection_manager.is_empty


def test_an_image_on_a_layer_made_background_is_deselected(main_window: MainWindow) -> None:
    window = main_window
    item = _screenshot(window)
    window.selection_manager.select(item)
    layer = window.scene.layer_manager.active_layer
    assert layer is not None
    window.scene.layer_manager.set_layer_type(layer.layer_id, "Background")
    assert window.selection_manager.is_empty


def test_an_annotation_on_a_background_layer_still_moves(main_window: MainWindow) -> None:
    from snapmock.items.rectangle_item import RectangleItem

    window = main_window
    _background_image(window)
    lm = window.scene.layer_manager
    background = lm.background_layer
    assert background is not None
    rect = RectangleItem(rect=QRectF(0, 0, 10, 10))
    window.scene.command_stack.push(AddItemCommand(window.scene, rect, background.layer_id))
    window.selection_manager.select(rect)
    assert window.selection_manager.items == [rect]


def test_a_duplicate_of_the_background_layer_holds_a_movable_image(
    main_window: MainWindow,
) -> None:
    """The route Doug's decision leaves for repositioning a capture."""
    from snapmock.commands.layer_commands import DuplicateLayerCommand

    window = main_window
    _background_image(window)
    lm = window.scene.layer_manager
    background = lm.background_layer
    assert background is not None
    window.scene.command_stack.push(DuplicateLayerCommand(window.scene, background.layer_id))
    copy = [i for i in window.scene.annotation_items() if i.layer_id != background.layer_id]
    assert len(copy) == 1
    window.selection_manager.select(copy[0])
    assert window.selection_manager.items == copy


# ---- Cut takes the pixels the user sees (end-to-end pass finding 16) ----


def _capture(window: MainWindow) -> RasterRegionItem:
    from snapmock.commands.layer_commands import CreateBackgroundLayerCommand

    pixmap = QPixmap(300, 200)
    pixmap.fill(QColor("green"))
    command = CreateBackgroundLayerCommand(window.scene, pixmap)
    window.scene.command_stack.push(command)
    return command.item


def test_cut_on_a_capture_erases_the_background_image(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """Doug's decision A of 09-17-26: Cut erases from the topmost visible layer with an
    image under the selection. A capture leaves an empty annotation layer active, and the
    cut erased nothing there and said nothing."""
    image = _capture(main_window)
    lm = main_window.scene.layer_manager
    assert lm.active_layer is not lm.background_layer
    _raster_selection(main_window, QRectF(10, 10, 50, 50))
    main_window._edit_cut()  # noqa: SLF001
    assert not unmet_messages
    assert image.pixmap.toImage().pixelColor(30, 30).alpha() == 0
    main_window.scene.command_stack.mark_clean()


def test_cut_on_a_capture_with_a_locked_background_is_refused(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    image = _capture(main_window)
    lm = main_window.scene.layer_manager
    background = lm.background_layer
    assert background is not None
    lm.set_locked(background.layer_id, True)
    _raster_selection(main_window, QRectF(10, 10, 50, 50))
    undo_before = main_window.scene.command_stack.undo_text
    main_window._edit_cut()  # noqa: SLF001
    assert (
        unmet_messages
        and "Cut needs an unlocked layer under the selection" in (unmet_messages[-1][1])
    )
    assert image.pixmap.toImage().pixelColor(30, 30).alpha() == 255
    assert main_window.scene.command_stack.undo_text == undo_before
    main_window.scene.command_stack.mark_clean()


def test_cut_with_no_image_under_the_selection_says_so(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    _capture(main_window)
    _raster_selection(main_window, QRectF(400, 300, 50, 50))
    undo_before = main_window.scene.command_stack.undo_text
    main_window._edit_cut()  # noqa: SLF001
    assert unmet_messages and "Cut needs an image under the selection" in (unmet_messages[-1][1])
    assert main_window.scene.command_stack.undo_text == undo_before
    main_window.scene.command_stack.mark_clean()
