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


# --- step 4: mutation ---


def _two(main_window: MainWindow) -> tuple[RectangleItem, RectangleItem]:
    """A locked rectangle and a free one, both selected."""
    scene = main_window.scene
    locked, free = _rect(scene), _rect(scene, 200, 10)
    locked.locked = True
    main_window.selection_manager.select_items([locked, free])
    return locked, free


def test_delete_and_cut_skip_a_locked_item_silently(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = main_window.scene
    locked, free = _two(main_window)
    main_window._edit_delete()  # noqa: SLF001
    assert scene.annotation_items() == [locked]
    assert unmet_messages == []
    main_window.selection_manager.select(locked)
    main_window._edit_delete()  # noqa: SLF001
    assert scene.annotation_items() == [locked]
    main_window._edit_cut()  # noqa: SLF001
    assert scene.annotation_items() == [locked]
    assert not main_window._clipboard.has_internal  # noqa: SLF001
    assert unmet_messages == []
    scene.command_stack.undo()
    main_window.selection_manager.select_items([locked, free])
    main_window._edit_cut()  # noqa: SLF001
    assert scene.annotation_items() == [locked]
    assert main_window._clipboard.has_internal  # noqa: SLF001


def test_a_pasted_locked_copy_is_selected_and_stays_locked(main_window: MainWindow) -> None:
    scene = main_window.scene
    item = _rect(scene)
    item.locked = True
    main_window.selection_manager.select(item)
    main_window._edit_copy()  # noqa: SLF001
    main_window._edit_paste_in_place()  # noqa: SLF001
    items = scene.annotation_items()
    assert len(items) == 2 and all(i.locked for i in items)
    assert main_window.selection_manager.count == 1
    assert main_window.selection_manager.items[0] is not item


def test_move_to_layer_skips_a_locked_item_and_refuses_a_locked_selection(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = main_window.scene
    first = scene.layer_manager.active_layer
    assert first is not None
    second = scene.layer_manager.add_layer("Layer 2")
    locked, free = _two(main_window)
    main_window._move_items_to_layer(second.layer_id)  # noqa: SLF001
    assert locked.layer_id == first.layer_id and free.layer_id == second.layer_id
    main_window.selection_manager.select(locked)
    main_window._move_items_to_layer(second.layer_id)  # noqa: SLF001
    assert locked.layer_id == first.layer_id
    assert unmet_messages == [("Move to Layer", "Move to Layer needs an unlocked item selected.")]


def test_align_uses_a_locked_item_as_the_reference_and_leaves_it(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    locked, free = _two(main_window)
    left = locked.sceneBoundingRect().left()
    main_window._arrange_align("left")  # noqa: SLF001
    assert locked.sceneBoundingRect().left() == left
    assert free.sceneBoundingRect().left() == left
    main_window.scene.command_stack.undo()
    assert free.sceneBoundingRect().left() != left
    main_window.selection_manager.select_items([locked])
    free.locked = True
    main_window.selection_manager.select_items([locked, free])
    main_window._arrange_align("left")  # noqa: SLF001
    main_window._arrange_distribute("horizontal")  # noqa: SLF001
    main_window._arrange_bring_to_front()  # noqa: SLF001
    main_window._arrange_flip_horizontal()  # noqa: SLF001
    main_window._arrange_align_canvas_center()  # noqa: SLF001
    assert [m[1] for m in unmet_messages] == [
        "Align needs an unlocked item selected.",
        "Distribute needs at least 3 items selected.",
        "Bring to Front needs an unlocked item selected.",
        "Flip Horizontal needs an unlocked item selected.",
        "Align to Canvas Center needs an unlocked item selected.",
    ]
    assert not free.flip_horizontal


def test_z_order_and_flip_reach_only_the_unlocked_item(main_window: MainWindow) -> None:
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    locked, free = _two(main_window)
    third = _rect(scene, 400, 10)
    main_window.selection_manager.select_items([locked, free])
    main_window._arrange_bring_to_front()  # noqa: SLF001
    assert layer.item_ids == [locked.item_id, third.item_id, free.item_id]
    main_window._arrange_flip_vertical()  # noqa: SLF001
    assert free.flip_vertical and not locked.flip_vertical


def test_group_and_ungroup_refuse_a_locked_item(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = main_window.scene
    locked, free = _two(main_window)
    main_window._arrange_group()  # noqa: SLF001
    assert unmet_messages == [("Group", "Group needs every selected item unlocked.")]
    assert len(scene.annotation_items()) == 2
    locked.locked = False
    main_window._arrange_group()  # noqa: SLF001
    from snapmock.items.group_item import GroupItem

    group = scene.annotation_items()[0]
    assert isinstance(group, GroupItem)
    group.locked = True
    main_window.selection_manager.select(group)
    main_window._arrange_ungroup()  # noqa: SLF001
    assert unmet_messages[-1] == ("Ungroup", "Ungroup needs an unlocked group selected.")
    assert scene.annotation_items() == [group]


def test_find_replace_color_leaves_a_locked_item(main_window: MainWindow) -> None:
    from snapmock.ui.find_replace_color_dialog import color_matches

    scene = main_window.scene
    locked, free = _two(main_window)
    matches = color_matches(scene, free.stroke_color)
    assert locked not in {item for item, _prop in matches}
    assert free in {item for item, _prop in matches}


def test_the_item_properties_dialog_and_the_marker_rows_refuse_a_locked_item(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    from snapmock.config.constants import DisplayMode
    from snapmock.items.numbered_step_item import NumberedStepItem

    scene = main_window.scene
    item = _rect(scene)
    item.locked = True
    main_window.selection_manager.select(item)
    main_window._show_item_properties()  # noqa: SLF001
    assert unmet_messages == [("Properties", "Properties needs an unlocked item selected.")]
    layer = scene.layer_manager.active_layer
    assert layer is not None
    step = NumberedStepItem()
    scene.command_stack.push(AddItemCommand(scene, step, layer.layer_id))
    step.locked = True
    main_window.selection_manager.select(step)
    mode = step.display_mode
    main_window._step_toggle_text_mode()  # noqa: SLF001
    assert step.display_mode is mode and mode is DisplayMode.NUMBER
    assert not main_window.open_marker_editor(step)
    assert [m[0] for m in unmet_messages[1:]] == ["Convert Display Mode", "Edit"]


def test_the_property_panel_rows_refuse_a_locked_item_and_the_checkbox_frees_it(
    qtbot: QtBot, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = SnapScene()
    sm = SelectionManager(scene)
    panel = PropertyPanel(sm, scene)
    qtbot.addWidget(panel)
    panel.show()
    locked, free = _rect(scene), _rect(scene, 200, 10)
    locked.locked = True
    sm.select(locked)
    x = locked.pos().x()
    panel._x_spin.setValue(300)  # noqa: SLF001
    assert locked.pos().x() == x
    assert panel._x_spin.value() == x  # noqa: SLF001
    assert unmet_messages and unmet_messages[-1][1].endswith("needs an unlocked item selected.")
    panel._stroke_w_spin.setValue(9)  # noqa: SLF001
    assert locked.stroke_width != 9
    # A mixed selection: the edit reaches the free item only, without a message
    unmet_messages.clear()
    sm.select_items([locked, free])
    panel._x_spin.setValue(300)  # noqa: SLF001
    assert free.pos().x() == 300 and locked.pos().x() == x
    assert unmet_messages == []
    # The checkbox is the way out
    sm.select(locked)
    assert panel._locked_check.isChecked()  # noqa: SLF001
    panel._locked_check.setChecked(False)  # noqa: SLF001
    assert not locked.locked
    panel._x_spin.setValue(300)  # noqa: SLF001
    assert locked.pos().x() == 300


def test_a_slider_drag_on_a_locked_item_is_refused_once_and_released(
    qtbot: QtBot, unmet_messages: list[tuple[str, str]]
) -> None:
    """Doug's display, 09-25-26: the message came back on every mouse move, since the
    modal box took the release the slider was waiting for."""
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionSlider

    scene = SnapScene()
    sm = SelectionManager(scene)
    panel = PropertyPanel(sm, scene)
    qtbot.addWidget(panel)
    panel.resize(360, 900)
    panel.show()
    qtbot.waitExposed(panel)
    item = _rect(scene)
    item.locked = True
    sm.select(item)
    # An earlier test may have left the section collapsed in the settings; the drag
    # needs the slider on screen with room to move
    panel._appearance_section.set_expanded(True)  # noqa: SLF001
    slider = panel._stroke_w_slider  # noqa: SLF001
    assert slider.isVisible() and slider.width() > 40
    width = item.stroke_width
    # The press lands on the handle wherever the active style draws it
    option = QStyleOptionSlider()
    slider.initStyleOption(option)
    handle = slider.style().subControlRect(
        QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, slider
    )
    grip = handle.center()

    # Sent to the slider itself: the window path of QTest resolves the widget under the
    # point, and in a full run the panel may be scrolled so the slider is off screen
    def _send(kind: QEvent.Type, pos: QPoint, button: Qt.MouseButton) -> None:
        event = QMouseEvent(
            kind,
            QPointF(pos),
            QPointF(slider.mapToGlobal(pos)),
            button,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(slider, event)

    _send(QEvent.Type.MouseButtonPress, grip, Qt.MouseButton.LeftButton)
    for dx in (0, 8, 16):
        _send(
            QEvent.Type.MouseMove,
            QPoint(slider.width() // 2 + dx, grip.y()),
            Qt.MouseButton.NoButton,
        )
    assert unmet_messages == [
        ("Stroke width slider", "Stroke width slider needs an unlocked item selected.")
    ]
    assert not slider.isSliderDown()
    assert item.stroke_width == width and slider.value() == int(width)
