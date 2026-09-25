"""Escape, a ladder of three rungs (General UI PRD 2.58; Doug's decision C of 09-25-26):
end the tool's own operation, else leave any other tool for the Select tool with the item
last added selected, else deselect all."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.scene import SnapScene
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.crop_tool import CropTool
from snapmock.tools.raster_select_tool import RasterSelectTool


def _draw(main_window: MainWindow) -> RectangleItem:
    """What a shape tool does on release: one AddItemCommand, nothing selected (2.5)."""
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 50, 40))
    item.setPos(100, 100)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


def test_the_scene_remembers_the_item_last_added_until_it_is_undone(qapp: object) -> None:
    scene = SnapScene(width=200, height=200)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    assert scene.last_added_item is None
    a, b = RectangleItem(), RectangleItem()
    scene.command_stack.push(AddItemCommand(scene, a, layer.layer_id))
    scene.command_stack.push(AddItemCommand(scene, b, layer.layer_id))
    assert scene.last_added_item is b
    scene.command_stack.undo()
    assert scene.last_added_item is None
    scene.command_stack.redo()
    assert scene.last_added_item is b


def test_escape_leaves_a_shape_tool_with_the_shape_just_drawn_selected(
    main_window: MainWindow,
) -> None:
    main_window.tool_manager.activate("rectangle")
    item = _draw(main_window)
    assert main_window.selection_manager.items == []
    main_window._edit_deselect()  # noqa: SLF001 — the Escape shortcut's slot
    assert main_window.tool_manager.active_tool_id == "select"
    assert main_window.selection_manager.items == [item]
    # The third rung: Escape under the Select tool deselects
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.selection_manager.items == []


def test_escape_after_undo_leaves_the_tool_with_nothing_selected(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("ellipse")
    _draw(main_window)
    main_window.scene.command_stack.undo()
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"
    assert main_window.selection_manager.items == []


def test_escape_does_not_select_a_shape_on_a_locked_layer(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("arrow")
    item = _draw(main_window)
    main_window.scene.layer_manager.set_locked(item.layer_id, True)
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"
    assert main_window.selection_manager.items == []


def test_escape_leaves_a_tool_that_drew_nothing(main_window: MainWindow) -> None:
    """A placing tool with no shape of its own behind it: the Select tool, nothing selected."""
    main_window.tool_manager.activate("stamp")
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"
    assert main_window.selection_manager.items == []


def test_escape_cancels_a_raster_selection_before_it_leaves_the_tool(
    main_window: MainWindow,
) -> None:
    main_window.tool_manager.activate("raster_select")
    tool = main_window.tool_manager.active_tool
    assert isinstance(tool, RasterSelectTool)
    tool.select_rect(QRectF(10, 10, 50, 50))
    assert tool.has_active_selection
    main_window._edit_deselect()  # noqa: SLF001
    assert not tool.has_active_selection
    assert main_window.tool_manager.active_tool_id == "raster_select"
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"


def test_escape_resets_a_crop_region_before_it_leaves_the_tool(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("crop")
    tool = main_window.tool_manager.active_tool
    assert isinstance(tool, CropTool)
    overlay = tool._overlay  # noqa: SLF001
    assert overlay is not None
    overlay.update_crop_rect(QRectF(10, 10, 50, 50))
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "crop"
    overlay = tool._overlay  # noqa: SLF001
    assert overlay is not None
    assert overlay.crop_rect == QRectF(QPointF(0, 0), main_window.scene.canvas_size)
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"


def test_escape_under_the_select_tool_with_nothing_selected_stays_put(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """The third rung with nothing to deselect: the message, not a switch or a selection."""
    main_window.tool_manager.activate("select")
    _draw(main_window)
    main_window._edit_deselect()  # noqa: SLF001
    assert main_window.tool_manager.active_tool_id == "select"
    assert main_window.selection_manager.items == []
    assert unmet_messages and unmet_messages[0][0] == "Deselect"
