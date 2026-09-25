"""Tests for ClipboardManager."""

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.clipboard_manager import ClipboardManager
from snapmock.core.scene import SnapScene
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


@pytest.fixture()
def clipboard(scene: SnapScene) -> ClipboardManager:
    return ClipboardManager(scene)


def test_clipboard_initially_empty(clipboard: ClipboardManager) -> None:
    assert not clipboard.has_internal
    assert clipboard.paste_items() == []


def test_copy_items(scene: SnapScene, clipboard: ClipboardManager) -> None:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem()
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    clipboard.copy_items([item])
    assert clipboard.has_internal
    data = clipboard.paste_items()
    assert len(data) == 1
    assert data[0]["type"] == "RectangleItem"


def test_clear_clipboard(scene: SnapScene, clipboard: ClipboardManager) -> None:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem()
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    clipboard.copy_items([item])
    clipboard.clear()
    assert not clipboard.has_internal


def test_paste_gives_the_copy_new_ids(main_window: MainWindow) -> None:
    """A pasted item is a new item; the original keeps its id (notes Section 16.10)."""
    from snapmock.commands.group_commands import GroupItemsCommand
    from snapmock.items.group_item import GroupItem

    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    a, b = RectangleItem(), RectangleItem()
    b.setPos(200, 0)
    for item in (a, b):
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    command = GroupItemsCommand(scene, [a, b], main_window.selection_manager)
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    main_window._edit_copy()  # noqa: SLF001
    main_window._edit_paste()  # noqa: SLF001
    pasted = [i for i in scene.annotation_items() if i is not group]
    assert len(pasted) == 1 and isinstance(pasted[0], GroupItem)
    old_ids = {group.item_id, a.item_id, b.item_id}
    new_ids = {pasted[0].item_id} | {m.item_id for m in pasted[0].descendants()}
    assert len(new_ids) == 3 and old_ids.isdisjoint(new_ids)
    assert len({i.item_id for i in scene.all_annotation_items()}) == 6


def _system_image(width: int = 30, height: int = 20) -> None:
    from PyQt6.QtGui import QColor, QImage

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("blue"))
    clipboard.setImage(image)


def test_pasted_system_image_becomes_the_background_of_an_empty_project(
    main_window: MainWindow,
) -> None:
    """Follow-up step 5: Edit > Paste of a system image on an empty project."""
    from snapmock.items.raster_region_item import RasterRegionItem

    scene = main_window.scene
    lm = scene.layer_manager
    marks = lm.layers[0]
    _system_image()
    main_window._edit_paste()  # noqa: SLF001
    background = lm.layers[0]
    assert background.is_background and lm.count == 2 and lm.active_layer is marks
    regions = [i for i in scene.annotation_items() if isinstance(i, RasterRegionItem)]
    assert len(regions) == 1 and regions[0].layer_id == background.layer_id
    assert (scene.canvas_size.width(), scene.canvas_size.height()) == (30, 20)
    # A second paste is a region on the active layer; with the pointer off the canvas its
    # top-left corner is at the viewport centre (Raster PRD 1.12)
    main_window._edit_paste()  # noqa: SLF001
    regions = [i for i in scene.annotation_items() if isinstance(i, RasterRegionItem)]
    assert len(regions) == 2 and lm.count == 2
    second = next(r for r in regions if r.layer_id == marks.layer_id)
    viewport = main_window.view.viewport()
    assert viewport is not None
    centre = main_window.view.mapToScene(viewport.rect().center())
    assert second.pos() == centre
    scene.command_stack.undo()
    scene.command_stack.undo()
    assert lm.count == 1 and lm.background_layer is None
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    clipboard.clear()


# --- the whole canvas: Copy with nothing selected, Select All on an empty layer, Copy All
# (General UI PRD 2.55, Raster PRD 1.11; Doug's decision A of 09-24-26) ---


def _clipboard_image_size() -> tuple[int, int]:
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    image = clipboard.image()
    return image.width(), image.height()


def _capture(main_window: MainWindow) -> None:
    """A capture as the app leaves it: the image on a Background layer, an empty layer active."""
    _system_image(30, 20)
    main_window._edit_paste()  # noqa: SLF001
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    clipboard.clear()
    main_window.clipboard.clear()
    assert main_window.scene.layer_manager.background_layer is not None
    assert not main_window.selection_manager.items


def test_copy_with_nothing_selected_copies_the_whole_canvas(main_window: MainWindow) -> None:
    _capture(main_window)
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size() == (30, 20)
    assert main_window.clipboard.has_raster


def test_select_all_is_a_raster_selection_of_the_whole_document(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    from snapmock.tools.raster_select_tool import RasterSelectTool

    _capture(main_window)
    main_window._edit_select_all()  # noqa: SLF001
    assert unmet_messages == []
    tool = main_window.tool_manager.active_tool
    assert isinstance(tool, RasterSelectTool) and tool.has_active_selection
    assert tool.selection_rect == main_window.scene.canvas_rect
    # The Background image itself is still never selected (2.46)
    assert not main_window.selection_manager.items
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size() == (30, 20)


def test_select_all_takes_the_whole_document_over_an_annotated_layer(
    main_window: MainWindow,
) -> None:
    """Decision B of 09-25-26: an annotated capture's Ctrl+A, Ctrl+C is the whole picture,
    not the annotations' region; Select All on Layer keeps the item selection."""
    from snapmock.tools.raster_select_tool import RasterSelectTool

    _capture(main_window)
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 10, 10))
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    main_window.selection_manager.select_items([item])
    main_window._edit_select_all()  # noqa: SLF001
    assert main_window.selection_manager.items == []
    tool = main_window.tool_manager.active_tool
    assert isinstance(tool, RasterSelectTool) and tool.has_active_selection
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size() == (30, 20)
    main_window.tool_manager.activate("select")
    main_window._edit_select_all_on_layer()  # noqa: SLF001
    assert main_window.selection_manager.items == [item]


def test_copy_all_copies_the_canvas_whatever_is_selected(main_window: MainWindow) -> None:
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 10, 10))
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    main_window.selection_manager.select_items([item])
    canvas = scene.canvas_size
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size()[0] < canvas.width()
    main_window._edit_copy_all()  # noqa: SLF001
    assert _clipboard_image_size() == (int(canvas.width()), int(canvas.height()))
    assert main_window.selection_manager.items == [item]


def test_copy_all_has_snagits_key_and_crop_to_canvas_moved() -> None:
    from snapmock.config.shortcuts import SHORTCUTS

    assert SHORTCUTS["edit.copy_all"] == "Ctrl+Shift+C"
    assert SHORTCUTS["image.crop_to_canvas"] == "Ctrl+Shift+X"
    keys = [k for k in SHORTCUTS.values() if k]
    assert len(keys) == len(set(keys))


def test_whole_canvas_copy_and_select_all_include_the_border(main_window: MainWindow) -> None:
    """Raster PRD 1.11: the flattened copy covers the output rectangle, as the export does."""
    from snapmock.tools.raster_select_tool import RasterSelectTool

    _capture(main_window)
    scene = main_window.scene
    scene.set_border_width(5)
    assert scene.output_rect.width() == 40 and scene.output_rect.height() == 30
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size() == (40, 30)
    main_window._edit_select_all()  # noqa: SLF001
    tool = main_window.tool_manager.active_tool
    assert isinstance(tool, RasterSelectTool) and tool.selection_rect == scene.output_rect
    main_window._edit_copy()  # noqa: SLF001
    assert _clipboard_image_size() == (40, 30)


# --- Paste at the pointer (Raster PRD 5.5.3, 9.3.1, 9.3.3, 9.3.4; 1.12) ---


def _point_at(main_window: MainWindow, x: int, y: int) -> QPointF:
    """Move the pointer over the viewport to (*x*, *y*) and return the scene point there.

    The window is shown first: a pointer position only counts on a visible viewport.
    """
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    main_window.show()
    view = main_window.view
    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(x, y),
        view.mapToGlobal(QPoint(x, y)).toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(event)
    pos = view.pointer_scene_pos
    assert pos is not None
    return pos


def _two_rectangles(main_window: MainWindow) -> tuple[RectangleItem, RectangleItem]:
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    a = RectangleItem(QRectF(0, 0, 50, 40))
    b = RectangleItem(QRectF(0, 0, 30, 30))
    a.setPos(100, 100)
    b.setPos(220, 160)
    for item in (a, b):
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return a, b


def _pasted(main_window: MainWindow, originals: tuple[RectangleItem, ...]) -> list[RectangleItem]:
    return [
        i
        for i in main_window.scene.annotation_items()
        if isinstance(i, RectangleItem) and i not in originals
    ]


def _joint_bounds(items: list[RectangleItem]) -> QRectF:
    bounds = items[0].sceneBoundingRect()
    for item in items[1:]:
        bounds = bounds.united(item.sceneBoundingRect())
    return bounds


def test_paste_puts_the_items_bounding_box_at_the_pointer(main_window: MainWindow) -> None:
    """9.3.1: the top-left of the joint bounding box lands where the pointer is, the
    arrangement kept, the copies selected under the Select tool."""
    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([a, b])
    main_window._edit_copy()  # noqa: SLF001
    main_window.tool_manager.activate("rectangle")
    anchor = _point_at(main_window, 40, 30)
    main_window._edit_paste()  # noqa: SLF001
    pasted = _pasted(main_window, (a, b))
    assert len(pasted) == 2
    bounds = _joint_bounds(pasted)
    assert bounds.topLeft() == anchor
    first, second = sorted(pasted, key=lambda i: i.pos().x())
    assert second.pos() - first.pos() == b.pos() - a.pos()
    assert set(main_window.selection_manager.items) == set(pasted)
    assert main_window.tool_manager.active_tool_id == "select"


def test_paste_twice_lands_at_the_pointer_each_time(main_window: MainWindow) -> None:
    """9.3.1: no cascade offset; the pointer decides."""
    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([a])
    main_window._edit_copy()  # noqa: SLF001
    first = _point_at(main_window, 10, 10)
    main_window._edit_paste()  # noqa: SLF001
    second = _point_at(main_window, 300, 200)
    main_window._edit_paste()  # noqa: SLF001
    pasted = _pasted(main_window, (a, b))
    assert len(pasted) == 2
    assert sorted(i.sceneBoundingRect().topLeft().x() for i in pasted) == sorted(
        (first.x(), second.x())
    )


def test_paste_from_a_context_menu_lands_at_the_right_click_point(
    main_window: MainWindow,
) -> None:
    """The row is chosen with the pointer over the menu, so the menu passes the point."""
    from PyQt6.QtCore import QPointF

    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([b])
    main_window._edit_copy()  # noqa: SLF001
    _point_at(main_window, 5, 5)
    main_window._edit_paste(at=QPointF(400, 300))  # noqa: SLF001
    pasted = _pasted(main_window, (a, b))
    assert len(pasted) == 1
    assert pasted[0].sceneBoundingRect().topLeft() == QPointF(400, 300)


def test_paste_with_the_pointer_off_the_canvas_lands_at_the_viewport_centre(
    main_window: MainWindow,
) -> None:
    """Edit > Paste, the Welcome card, or a shortcut with the pointer elsewhere."""
    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([a])
    main_window._edit_copy()  # noqa: SLF001
    _point_at(main_window, 5, 5)
    main_window.view.leaveEvent(None)
    assert main_window.view.pointer_scene_pos is None
    main_window._edit_paste()  # noqa: SLF001
    pasted = _pasted(main_window, (a, b))
    viewport = main_window.view.viewport()
    assert viewport is not None
    centre = main_window.view.mapToScene(viewport.rect().center())
    assert len(pasted) == 1
    assert pasted[0].sceneBoundingRect().topLeft() == centre


def test_paste_in_place_keeps_the_original_positions(main_window: MainWindow) -> None:
    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([a, b])
    main_window._edit_copy()  # noqa: SLF001
    _point_at(main_window, 5, 5)
    main_window._edit_paste_in_place()  # noqa: SLF001
    pasted = _pasted(main_window, (a, b))
    assert sorted(i.pos().x() for i in pasted) == [100, 220]
    assert sorted(i.pos().y() for i in pasted) == [100, 160]
    assert set(main_window.selection_manager.items) == set(pasted)


def test_raster_paste_lands_at_the_pointer_and_in_place_at_its_source(
    main_window: MainWindow,
) -> None:
    """5.5.3: a raster copy at the pointer; Paste in Place at the source rectangle."""
    from PyQt6.QtGui import QColor, QImage

    from snapmock.items.raster_region_item import RasterRegionItem

    image = QImage(20, 10, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    main_window.clipboard.copy_raster_region(image, QRectF(50, 60, 20, 10))
    anchor = _point_at(main_window, 70, 80)
    main_window._edit_paste()  # noqa: SLF001
    main_window._edit_paste_in_place()  # noqa: SLF001
    regions = [i for i in main_window.scene.annotation_items() if isinstance(i, RasterRegionItem)]
    assert sorted((r.pos().x(), r.pos().y()) for r in regions) == sorted(
        [(anchor.x(), anchor.y()), (50.0, 60.0)]
    )


def test_system_text_pastes_at_the_pointer(main_window: MainWindow) -> None:
    """9.3.4: the text item's top-left corner at the pointer."""
    from snapmock.items.text_item import TextItem

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    main_window.clipboard.clear()
    clipboard.setText("hello")
    anchor = _point_at(main_window, 120, 90)
    main_window._edit_paste()  # noqa: SLF001
    texts = [i for i in main_window.scene.annotation_items() if isinstance(i, TextItem)]
    assert len(texts) == 1 and texts[0].pos() == anchor
    clipboard.clear()


def test_edit_menu_paste_action_pastes(main_window: MainWindow) -> None:
    """The action's triggered signal passes a checked flag; it must not become the anchor."""
    a, b = _two_rectangles(main_window)
    main_window.selection_manager.select_items([a])
    main_window._edit_copy()  # noqa: SLF001
    main_window._actions["edit.paste"].trigger()  # noqa: SLF001
    assert len(_pasted(main_window, (a, b))) == 1
