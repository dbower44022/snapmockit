"""Tests for ClipboardManager."""

import pytest
from PyQt6.QtCore import QRectF
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
    # A second paste is a region on the active layer at the viewport centre
    main_window._edit_paste()  # noqa: SLF001
    regions = [i for i in scene.annotation_items() if isinstance(i, RasterRegionItem)]
    assert len(regions) == 2 and lm.count == 2
    second = next(r for r in regions if r.layer_id == marks.layer_id)
    viewport = main_window.view.viewport()
    assert viewport is not None
    centre = main_window.view.mapToScene(viewport.rect().center())
    assert second.pos().x() == centre.x() - 15 and second.pos().y() == centre.y() - 10
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


def test_select_all_on_an_empty_layer_is_a_raster_selection_of_the_canvas(
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


def test_select_all_still_selects_the_items_of_the_active_layer(main_window: MainWindow) -> None:
    _capture(main_window)
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem()
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    main_window._edit_select_all()  # noqa: SLF001
    assert main_window.selection_manager.items == [item]
    assert main_window.tool_manager.active_tool_id != "raster_select"


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
