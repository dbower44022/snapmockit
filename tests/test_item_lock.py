"""The per-item lock (Technical Architecture PRD 3.1.4; General UI PRD 8 and 10.2;
Navigation PRD Section 2), Doug's decision B of 09-25-26: a locked item can be selected
and is unlocked where it was locked; every move and edit refuses it."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.group_commands import GroupItemsCommand
from snapmock.core.clipboard_manager import ClipboardManager
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.io.project_serializer import load_project, save_project
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.ui.property_panel import PropertyPanel


def _rect(scene: SnapScene, x: float = 10, y: float = 10) -> RectangleItem:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 100, 60))
    item.fill_color = item.stroke_color
    item.setPos(x, y)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    return item


# --- step 2: the model ---


def test_is_locked_reads_the_item_the_group_and_the_layer(scene: SnapScene) -> None:
    a, b = _rect(scene), _rect(scene, 200, 10)
    assert not scene.is_locked(a)
    a.locked = True
    assert scene.is_locked(a)
    assert not scene.is_locked(b)
    a.locked = False
    command = GroupItemsCommand(scene, [a, b])
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    group.locked = True
    assert scene.is_locked(a) and scene.is_locked(b) and scene.is_locked(group)
    group.locked = False
    assert not scene.is_locked(a)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.layer_manager.set_locked(layer.layer_id, True)
    assert scene.is_locked(a) and scene.is_locked(group)
    # The layer is read live: unlocking it leaves the item's own flag as it was
    scene.layer_manager.set_locked(layer.layer_id, False)
    assert not scene.is_locked(a) and not a.locked


def test_the_lock_survives_a_save_and_a_missing_key_reads_unlocked(
    scene: SnapScene, tmp_path: Path
) -> None:
    locked, free = _rect(scene), _rect(scene, 200, 10)
    locked.locked = True
    path = tmp_path / "lock.smk"
    save_project(scene, path)
    loaded = load_project(path)
    by_id = {i.item_id: i for i in loaded.all_annotation_items()}
    assert by_id[locked.item_id].locked
    assert not by_id[free.item_id].locked
    # An entry from a build before the key, and one with the key absent, is unlocked
    data = locked.serialize()
    del data["locked"]
    assert not RectangleItem.deserialize(data).locked


def test_a_clone_and_a_pasted_copy_keep_the_lock(scene: SnapScene) -> None:
    item = _rect(scene)
    item.locked = True
    assert item.clone().locked
    clipboard = ClipboardManager(scene)
    clipboard.copy_items([item])
    assert clipboard.paste_items()[0]["locked"] is True


def test_duplicate_keeps_the_lock(main_window: MainWindow) -> None:
    item = _rect(main_window.scene)
    item.locked = True
    main_window.selection_manager.select(item)
    main_window._edit_duplicate()  # noqa: SLF001
    items = main_window.scene.annotation_items()
    assert len(items) == 2
    assert all(i.locked for i in items)


def test_the_context_menu_row_and_the_checkbox_both_undo(
    main_window: MainWindow, qtbot: QtBot
) -> None:
    scene = main_window.scene
    a, b = _rect(scene), _rect(scene, 200, 10)
    main_window.selection_manager.select_items([a, b])
    main_window._toggle_item_lock()  # noqa: SLF001
    assert a.locked and b.locked
    scene.command_stack.undo()
    assert not a.locked and not b.locked
    scene.command_stack.redo()
    assert a.locked and b.locked
    main_window._toggle_item_lock()  # noqa: SLF001
    assert not a.locked and not b.locked

    sm = SelectionManager(scene)
    panel = PropertyPanel(sm, scene)
    qtbot.addWidget(panel)
    sm.select(a)
    panel._locked_check.setChecked(True)  # noqa: SLF001
    assert a.locked
    scene.command_stack.undo()
    assert not a.locked
    assert isinstance(a, SnapGraphicsItem)
