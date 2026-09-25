"""Context menu builder functions for canvas, items, and layer panel.

No row is ever disabled (General UI PRD 1.3): each handler checks its own
requirements and shows the unmet-requirement message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMenu

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF

    from snapmock.core.layer_manager import LayerManager
    from snapmock.main_window import MainWindow


def build_canvas_context_menu(parent: MainWindow, scene_pos: QPointF | None = None) -> QMenu:
    """Build the context menu shown when right-clicking empty canvas (PRD §10.1).

    *scene_pos* is the right-click point: Paste puts the content there (Raster PRD 9.3.1),
    since by the time the row is chosen the pointer is over the menu, not the canvas.
    """
    menu = QMenu(parent)

    paste_action = menu.addAction("Paste")
    if paste_action is not None:
        paste_action.triggered.connect(lambda: parent._edit_paste(at=scene_pos))  # noqa: SLF001

    paste_in_place_action = menu.addAction("Paste in Place")
    if paste_in_place_action is not None:
        paste_in_place_action.triggered.connect(parent._edit_paste_in_place)  # noqa: SLF001

    menu.addSeparator()

    select_all_action = menu.addAction("Select All")
    if select_all_action is not None:
        select_all_action.triggered.connect(parent._edit_select_all)  # noqa: SLF001

    menu.addSeparator()

    canvas_props_action = menu.addAction("Canvas Properties...")
    if canvas_props_action is not None:
        canvas_props_action.triggered.connect(parent._show_canvas_properties)  # noqa: SLF001

    menu.addSeparator()

    zoom_in_action = menu.addAction("Zoom In")
    if zoom_in_action is not None:
        zoom_in_action.triggered.connect(parent.view.zoom_in)

    zoom_out_action = menu.addAction("Zoom Out")
    if zoom_out_action is not None:
        zoom_out_action.triggered.connect(parent.view.zoom_out)

    fit_action = menu.addAction("Fit to Window")
    if fit_action is not None:
        fit_action.triggered.connect(parent.view.fit_in_view_all)

    zoom_100_action = menu.addAction("Zoom to 100%")
    if zoom_100_action is not None:
        zoom_100_action.triggered.connect(lambda: parent.view.set_zoom(100))

    return menu


def build_item_context_menu(parent: MainWindow, scene_pos: QPointF | None = None) -> QMenu:
    """Build the context menu shown when right-clicking a selected item (PRD §10.2).

    *scene_pos* is the right-click point, where Paste puts the content.
    """
    menu = QMenu(parent)

    # --- Clipboard actions ---
    cut_action = menu.addAction("Cut")
    if cut_action is not None:
        cut_action.triggered.connect(parent._edit_cut)  # noqa: SLF001

    copy_action = menu.addAction("Copy")
    if copy_action is not None:
        copy_action.triggered.connect(parent._edit_copy)  # noqa: SLF001

    paste_action = menu.addAction("Paste")
    if paste_action is not None:
        paste_action.triggered.connect(lambda: parent._edit_paste(at=scene_pos))  # noqa: SLF001

    duplicate_action = menu.addAction("Duplicate")
    if duplicate_action is not None:
        duplicate_action.triggered.connect(parent._edit_duplicate)  # noqa: SLF001

    delete_action = menu.addAction("Delete")
    if delete_action is not None:
        delete_action.triggered.connect(parent._edit_delete)  # noqa: SLF001

    menu.addSeparator()

    # --- Arrange actions ---
    front_action = menu.addAction("Bring to Front")
    if front_action is not None:
        front_action.triggered.connect(parent._arrange_bring_to_front)  # noqa: SLF001

    forward_action = menu.addAction("Bring Forward")
    if forward_action is not None:
        forward_action.triggered.connect(parent._arrange_bring_forward)  # noqa: SLF001

    backward_action = menu.addAction("Send Backward")
    if backward_action is not None:
        backward_action.triggered.connect(parent._arrange_send_backward)  # noqa: SLF001

    back_action = menu.addAction("Send to Back")
    if back_action is not None:
        back_action.triggered.connect(parent._arrange_send_to_back)  # noqa: SLF001

    menu.addSeparator()

    # --- Move to Layer submenu ---
    move_to_layer_menu = menu.addMenu("Move to Layer")
    if move_to_layer_menu is not None:
        for layer in parent.scene.layer_manager.layers:
            layer_action = move_to_layer_menu.addAction(layer.name)
            if layer_action is not None:
                lid = layer.layer_id
                layer_action.triggered.connect(
                    lambda _checked=False, t=lid: parent._move_items_to_layer(t)  # noqa: SLF001
                )

    menu.addSeparator()

    # --- Lock/Unlock ---
    from snapmock.items.base_item import SnapGraphicsItem

    first_item = None
    for item in parent.selection_manager.items:
        if isinstance(item, SnapGraphicsItem):
            first_item = item
            break
    lock_text = "Unlock Item" if (first_item is not None and first_item.locked) else "Lock Item"
    lock_action = menu.addAction(lock_text)
    if lock_action is not None:
        lock_action.triggered.connect(parent._toggle_item_lock)  # noqa: SLF001

    menu.addSeparator()

    # --- Align submenu ---
    align_menu = menu.addMenu("Align")
    if align_menu is not None:
        for label, alignment in [
            ("Align Left", "left"),
            ("Align Center Horizontal", "center_h"),
            ("Align Right", "right"),
            ("Align Top", "top"),
            ("Align Middle Vertical", "middle_v"),
            ("Align Bottom", "bottom"),
        ]:
            a = align_menu.addAction(label)
            if a is not None:
                a.triggered.connect(
                    lambda _checked=False, al=alignment: parent._arrange_align(al)  # noqa: SLF001
                )

    # --- Distribute submenu ---
    distribute_menu = menu.addMenu("Distribute")
    if distribute_menu is not None:
        dist_h = distribute_menu.addAction("Distribute Horizontally")
        if dist_h is not None:
            dist_h.triggered.connect(
                lambda: parent._arrange_distribute("horizontal")  # noqa: SLF001
            )
        dist_v = distribute_menu.addAction("Distribute Vertically")
        if dist_v is not None:
            dist_v.triggered.connect(
                lambda: parent._arrange_distribute("vertical")  # noqa: SLF001
            )

    menu.addSeparator()

    # --- Flip actions ---
    flip_h_action = menu.addAction("Flip Horizontal")
    if flip_h_action is not None:
        flip_h_action.triggered.connect(parent._arrange_flip_horizontal)  # noqa: SLF001

    flip_v_action = menu.addAction("Flip Vertical")
    if flip_v_action is not None:
        flip_v_action.triggered.connect(parent._arrange_flip_vertical)  # noqa: SLF001

    menu.addSeparator()

    # --- Numbered step rows (Numbered Steps, Stamps & Emoji PRD 2.8) ---
    from snapmock.config.constants import DisplayMode
    from snapmock.items.numbered_step_item import NumberedStepItem

    selected = [i for i in parent.selection_manager.items if isinstance(i, SnapGraphicsItem)]
    if len(selected) == 1 and isinstance(selected[0], NumberedStepItem):
        step = selected[0]
        renumber_action = menu.addAction("Renumber All Steps")
        if renumber_action is not None:
            renumber_action.triggered.connect(parent.renumber_all_steps)
        start_action = menu.addAction("Set as Starting Number")
        if start_action is not None:
            start_action.triggered.connect(parent._step_set_as_starting_number)  # noqa: SLF001
        convert_text = (
            "Convert to Number Mode"
            if step.display_mode is DisplayMode.TEXT
            else "Convert to Text Mode"
        )
        convert_action = menu.addAction(convert_text)
        if convert_action is not None:
            convert_action.triggered.connect(parent._step_toggle_text_mode)  # noqa: SLF001
        menu.addSeparator()

    # --- Stamp rows (PRD 3.7): Flip Horizontal and Flip Vertical are above already ---
    from snapmock.items.stamp_item import StampItem

    if len(selected) == 1 and isinstance(selected[0], StampItem):
        change_action = menu.addAction("Change Stamp...")
        if change_action is not None:
            change_action.triggered.connect(parent._stamp_change)  # noqa: SLF001
        reset_action = menu.addAction("Reset Size")
        if reset_action is not None:
            reset_action.triggered.connect(parent._stamp_reset_size)  # noqa: SLF001
        menu.addSeparator()

    # --- Emoji rows (PRD 4.6): Flip Horizontal and Flip Vertical are above already ---
    from snapmock.items.emoji_item import EmojiItem

    if len(selected) == 1 and isinstance(selected[0], EmojiItem):
        change_emoji_action = menu.addAction("Change Emoji...")
        if change_emoji_action is not None:
            change_emoji_action.triggered.connect(parent._emoji_change)  # noqa: SLF001
        reset_emoji_action = menu.addAction("Reset Size")
        if reset_emoji_action is not None:
            reset_emoji_action.triggered.connect(parent._emoji_reset_size)  # noqa: SLF001
        menu.addSeparator()

    # --- Properties ---
    props_action = menu.addAction("Properties...")
    if props_action is not None:
        props_action.triggered.connect(parent._show_item_properties)  # noqa: SLF001

    return menu


def build_layer_panel_context_menu(
    parent: MainWindow, layer_manager: LayerManager, layer_id: str
) -> QMenu:
    """Build the context menu shown when right-clicking a layer row (PRD §10.3)."""
    menu = QMenu(parent)
    layer = layer_manager.layer_by_id(layer_id)
    if layer is None:
        return menu

    # --- New Layer Above / Below ---
    new_above_action = menu.addAction("New Layer Above")
    if new_above_action is not None:
        new_above_action.triggered.connect(
            lambda: parent._layer_new_relative(layer_id, above=True)  # noqa: SLF001
        )

    new_below_action = menu.addAction("New Layer Below")
    if new_below_action is not None:
        new_below_action.triggered.connect(
            lambda: parent._layer_new_relative(layer_id, above=False)  # noqa: SLF001
        )

    menu.addSeparator()

    # --- Duplicate / Delete ---
    dup_action = menu.addAction("Duplicate Layer")
    if dup_action is not None:
        dup_action.triggered.connect(parent._layer_duplicate)  # noqa: SLF001

    delete_action = menu.addAction("Delete Layer")
    if delete_action is not None:
        delete_action.triggered.connect(parent._layer_delete)  # noqa: SLF001

    menu.addSeparator()

    # --- Rename ---
    rename_action = menu.addAction("Rename Layer")
    if rename_action is not None:
        rename_action.triggered.connect(parent._layer_rename)  # noqa: SLF001

    menu.addSeparator()

    # --- Merge actions ---
    merge_down_action = menu.addAction("Merge Down")
    if merge_down_action is not None:
        merge_down_action.triggered.connect(parent._layer_merge_down)  # noqa: SLF001

    merge_visible_action = menu.addAction("Merge Visible")
    if merge_visible_action is not None:
        merge_visible_action.triggered.connect(parent._layer_merge_visible)  # noqa: SLF001

    flatten_action = menu.addAction("Flatten All")
    if flatten_action is not None:
        flatten_action.triggered.connect(parent._layer_flatten)  # noqa: SLF001

    menu.addSeparator()

    # --- Lock / Unlock ---
    lock_text = "Unlock Layer" if layer.locked else "Lock Layer"
    lock_action = menu.addAction(lock_text)
    if lock_action is not None:
        lock_action.triggered.connect(
            lambda: parent._toggle_layer_lock(layer_id)  # noqa: SLF001
        )

    # --- Hide / Show ---
    vis_text = "Show Layer" if not layer.visible else "Hide Layer"
    vis_action = menu.addAction(vis_text)
    if vis_action is not None:
        vis_action.triggered.connect(
            lambda: parent._toggle_layer_visibility(layer_id)  # noqa: SLF001
        )

    menu.addSeparator()

    # --- Properties ---
    props_action = menu.addAction("Layer Properties...")
    if props_action is not None:
        lid = layer_id
        props_action.triggered.connect(
            lambda _checked=False, t=lid: parent._show_layer_properties(t)  # noqa: SLF001
        )

    return menu
