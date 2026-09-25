"""EmojiTool, the picker, its Tool Options Bar, and emoji editing (Numbered Steps, Stamps &
Emoji PRD 4.2, 4.3, 4.5, 4.6, 4.9; kickoff Phase 3 steps 2 and 3)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QFontDatabase, QKeySequence, QMouseEvent
from PyQt6.QtWidgets import QCheckBox, QMenu, QSpinBox, QToolButton
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.marker_commands import ChangeEmojiCommand
from snapmock.config.shortcuts import SHORTCUTS
from snapmock.core.emoji_data import SKIN_TONE_MODIFIERS, SkinTone
from snapmock.core.scene import SnapScene
from snapmock.items import emoji_item as emoji_item_module
from snapmock.items.emoji_item import EmojiItem
from snapmock.main_window import MainWindow
from snapmock.tools import numbered_step_tool as animation_module
from snapmock.tools.emoji_tool import NO_EMOJI_HINT, POP_IN_MS, EmojiTool, animate_pop_in
from snapmock.ui.context_menus import build_item_context_menu
from snapmock.ui.emoji_picker import RECENT_MAX, EmojiPicker, SkinTonePalette
from snapmock.ui.tool_options_bar import ToolOptionsBar

Button = Qt.MouseButton
Modifier = Qt.KeyboardModifier
THUMBS_UP = "\U0001f44d"
GRIN = "\U0001f600"
DOG = "\U0001f436"


@pytest.fixture(autouse=True)
def _no_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(animation_module, "ANIMATIONS_ENABLED", False)
    emoji_item_module.reset_emoji_font_cache()
    yield  # type: ignore[misc]
    emoji_item_module.reset_emoji_font_cache()


def _require_font() -> None:
    if not any("emoji" in f.casefold() for f in QFontDatabase.families()):
        pytest.skip("no colour emoji font installed")


def _tool(window: MainWindow, chars: str | None = THUMBS_UP) -> EmojiTool:
    window.tool_manager.activate("emoji")
    tool = window.tool_manager.tool("emoji")
    assert isinstance(tool, EmojiTool)
    if chars:
        tool.set_active_emoji(chars)
    return tool


def _bar(window: MainWindow) -> ToolOptionsBar:
    return window._tool_options  # noqa: SLF001


def _event(kind: QEvent.Type, window: MainWindow, scene_pos: QPointF) -> QMouseEvent:
    view_pos = QPointF(window.view.mapFromScene(scene_pos))
    return QMouseEvent(kind, view_pos, Button.LeftButton, Button.LeftButton, Modifier.NoModifier)


def _press(window: MainWindow, p: QPointF) -> None:
    window.tool_manager.handle_mouse_press(_event(QEvent.Type.MouseButtonPress, window, p))


def _move(window: MainWindow, p: QPointF) -> None:
    window.tool_manager.handle_mouse_move(_event(QEvent.Type.MouseMove, window, p))


def _release(window: MainWindow, p: QPointF) -> None:
    window.tool_manager.handle_mouse_release(_event(QEvent.Type.MouseButtonRelease, window, p))


def _click(window: MainWindow, p: QPointF) -> None:
    _press(window, p)
    _release(window, p)


def _double_click(window: MainWindow, p: QPointF) -> None:
    window.tool_manager.handle_mouse_double_click(
        _event(QEvent.Type.MouseButtonDblClick, window, p)
    )


def _emoji(window: MainWindow) -> list[EmojiItem]:
    found = [i for i in window.scene.annotation_items() if isinstance(i, EmojiItem)]
    return list(reversed(found))


def _menu_texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


# --- the nineteenth tool (General UI PRD 3.7, 17.3; Technical Architecture PRD 3.3) ---


def test_emoji_is_the_nineteenth_tool_after_stamp_with_shift_e(main_window: MainWindow) -> None:
    ids = main_window.tool_manager.tool_ids
    assert len(ids) == 22  # twenty-two since the Border tool (Navigation PRD Section 10)
    assert ids.index("emoji") == ids.index("stamp") + 1
    tool = main_window.tool_manager.tool("emoji")
    assert isinstance(tool, EmojiTool)
    assert tool.display_name == "Emoji"
    assert SHORTCUTS["tool.emoji"] == "Shift+E"
    action = main_window._tool_actions["emoji"]  # noqa: SLF001
    assert action.shortcut() == QKeySequence("Shift+E")
    assert not action.icon().isNull()
    button = main_window._toolbar._buttons["emoji"]  # noqa: SLF001
    assert not button.icon().isNull()


# --- placement (Section 4.3) ---


def test_hints_cursor_and_no_emoji_route(main_window: MainWindow) -> None:
    _require_font()
    tool = _tool(main_window, None)
    assert tool.active_emoji is None
    assert tool.status_hint == NO_EMOJI_HINT
    assert tool.cursor == Qt.CursorShape.CrossCursor
    _click(main_window, QPointF(100, 100))
    assert _emoji(main_window) == []
    picker = tool.picker
    assert isinstance(picker, EmojiPicker) and not picker.isHidden()
    picker.hide()
    tool.set_active_emoji(THUMBS_UP)
    assert tool.status_hint == "Click to place Thumbs up. Drag to set size."
    assert not tool.cursor.pixmap().isNull()  # type: ignore[union-attr]


def test_click_places_the_active_emoji_with_the_session_tone(main_window: MainWindow) -> None:
    _require_font()
    tool = _tool(main_window)
    _click(main_window, QPointF(100, 120))
    tool.set_skin_tone(SkinTone.DARK)
    _click(main_window, QPointF(200, 120))
    tool.set_active_emoji(GRIN)  # takes no tone
    _click(main_window, QPointF(300, 120))
    items = _emoji(main_window)
    assert [i.emoji_char for i in items] == [
        THUMBS_UP,
        THUMBS_UP + SKIN_TONE_MODIFIERS[SkinTone.DARK],
        GRIN,
    ]
    assert items[0].pos() == QPointF(100, 120)
    assert items[0].emoji_size == 48.0
    assert items[1].skin_tone is SkinTone.DARK
    assert items[2].emoji_name == "Grinning face"
    assert main_window.tool_manager.active_tool_id == "emoji"
    assert tool.status_hint == "Placed Grinning face. Click to place another."
    main_window.scene.command_stack.undo()
    assert len(_emoji(main_window)) == 2


def test_drag_fits_the_square_in_the_rectangle(main_window: MainWindow) -> None:
    _require_font()
    _tool(main_window)
    _press(main_window, QPointF(100, 100))
    _move(main_window, QPointF(220, 160))
    _release(main_window, QPointF(220, 160))
    (item,) = _emoji(main_window)
    assert item.emoji_size == pytest.approx(60.0)
    assert item.pos() == QPointF(160, 130)
    _press(main_window, QPointF(300, 300))
    _move(main_window, QPointF(304, 303))
    _release(main_window, QPointF(304, 303))
    assert _emoji(main_window)[-1].emoji_size == 48.0  # under ten pixels: a click


def test_placement_takes_the_creation_defaults(main_window: MainWindow) -> None:
    _require_font()
    tool = _tool(main_window)
    tool.creation_defaults.update(
        {"emoji_size": 96.0, "opacity_pct": 40.0, "flip_vertical": True, "shadow_enabled": True}
    )
    _click(main_window, QPointF(10, 10))
    (item,) = _emoji(main_window)
    assert item.emoji_size == 96.0
    assert item.opacity_pct == pytest.approx(40.0)
    assert item.flip_vertical is True
    assert item.shadow_enabled is True


def test_no_colour_emoji_font_explains_through_the_message(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(emoji_item_module, "_font_family_cache", None)
    monkeypatch.setattr(emoji_item_module, "_font_family_checked", True)
    _tool(main_window)
    _click(main_window, QPointF(10, 10))
    assert _emoji(main_window) == []
    assert unmet_messages[-1] == ("Emoji", "Emoji needs a colour emoji font installed.")


def test_locked_layer_refuses_with_the_message(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    _require_font()
    _tool(main_window)
    layer = main_window.scene.layer_manager.active_layer
    assert layer is not None
    main_window.scene.layer_manager.set_locked(layer.layer_id, True)
    _click(main_window, QPointF(10, 10))
    assert _emoji(main_window) == []
    assert unmet_messages[-1] == ("Emoji", "Emoji needs an unlocked active layer.")


def test_pop_in_animation_runs_to_scale_one(
    qtbot: QtBot, scene: SnapScene, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(animation_module, "ANIMATIONS_ENABLED", True)
    item = EmojiItem(GRIN)
    scene.addItem(item)
    animation = animate_pop_in(item, scene)
    assert animation is not None
    assert 0.0 < item.scale() <= 1.1 + 1e-6
    # Drive the clock by hand: the overshoot at 70 percent, then the end (deterministic
    # under a loaded machine, unlike waiting on the timer)
    animation.setCurrentTime(int(POP_IN_MS * 0.7))
    assert item.scale() == pytest.approx(1.1, abs=0.02)
    animation.setCurrentTime(POP_IN_MS)
    assert item.scale() == 1.0


# --- the picker (Section 4.2) ---


def test_picker_groups_grid_search_and_messages(qtbot: QtBot) -> None:
    _require_font()
    picker = EmojiPicker(popup=False)
    qtbot.addWidget(picker)
    picker.show()
    tabs = [picker.tabs.tabText(i) for i in range(picker.tabs.count())]
    assert tabs[0] == "Smileys & Emotion" and tabs[-1] == "Flags" and len(tabs) == 9
    assert GRIN in picker.visible_chars()
    picker.set_group("Animals & Nature")
    assert DOG in picker.visible_chars()
    assert picker.recent_list.isHidden()  # nothing used yet
    picker.search_edit.setText("thumbs")
    assert THUMBS_UP in picker.visible_chars()
    assert picker.tabs.isHidden()  # a search spans every category
    picker.search_edit.setText("zzqx-nothing")
    assert picker.visible_chars() == []
    assert not picker.empty_label.isHidden()
    assert "zzqx-nothing" in picker.empty_label.text()
    picker.search_edit.setText("")
    assert picker.current_group == "Animals & Nature"  # the open category is remembered


def test_picker_click_chooses_and_the_recent_row_keeps_24_most_recent_first(qtbot: QtBot) -> None:
    _require_font()
    picker = EmojiPicker(popup=False)
    qtbot.addWidget(picker)
    picker.show()
    chosen: list[str] = []
    picker.emoji_chosen.connect(chosen.append)
    item = picker.grid.item(0)
    assert item is not None
    picker.grid.itemClicked.emit(item)
    assert chosen == [GRIN]
    assert picker.isHidden()
    for n in range(30):
        picker.note_used(chr(0x1F600 + n))
    assert len(picker.recent) == RECENT_MAX
    assert picker.recent[0] == chr(0x1F600 + 29)
    picker.note_used(GRIN)
    assert picker.recent[0] == GRIN and picker.recent.count(GRIN) == 1
    picker.show()
    assert not picker.recent_list.isHidden()
    assert picker.recent_list.count() == RECENT_MAX


def test_picker_skin_tone_palette_and_session_memory(qtbot: QtBot) -> None:
    _require_font()
    picker = EmojiPicker(popup=False)
    qtbot.addWidget(picker)
    picker.show()
    picker.set_group("People & Body")
    grin_item = None
    thumbs_item = None
    for i in range(picker.grid.count()):
        item = picker.grid.item(i)
        assert item is not None
        if item.data(Qt.ItemDataRole.UserRole) == THUMBS_UP:
            thumbs_item = item
    assert thumbs_item is not None
    picker.set_group("Smileys & Emotion")
    grin_item = picker.grid.item(0)
    assert grin_item is not None
    assert picker.show_skin_tone_palette(grin_item) is None  # a grin takes no tone
    picker.set_group("People & Body")
    for i in range(picker.grid.count()):
        item = picker.grid.item(i)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == THUMBS_UP:
            thumbs_item = item
    palette = picker.show_skin_tone_palette(thumbs_item)  # type: ignore[arg-type]
    assert isinstance(palette, SkinTonePalette)
    tones: list[SkinTone] = []
    chosen: list[str] = []
    picker.skin_tone_chosen.connect(tones.append)
    picker.emoji_chosen.connect(chosen.append)
    palette.buttons[SkinTone.MEDIUM].click()
    assert tones == [SkinTone.MEDIUM]
    assert chosen == [THUMBS_UP + SKIN_TONE_MODIFIERS[SkinTone.MEDIUM]]
    assert picker.skin_tone is SkinTone.MEDIUM
    picker.show()
    assert (
        THUMBS_UP + SKIN_TONE_MODIFIERS[SkinTone.MEDIUM] in picker.visible_chars()
    )  # shown toned
    picker.set_current(THUMBS_UP)
    current = picker.grid.currentItem()
    assert current is not None and THUMBS_UP in str(current.data(Qt.ItemDataRole.UserRole))


# --- the Tool Options Bar (Section 4.5) ---


def test_bar_shows_preview_name_tones_and_the_section_4_5_controls(
    main_window: MainWindow,
) -> None:
    _require_font()
    tool = _tool(main_window)
    bar = _bar(main_window)
    widgets = bar.shared_widgets
    assert list(widgets) == [
        "emoji_size",
        "opacity_pct",
        "flip_horizontal",
        "flip_vertical",
        "shadow_enabled",
    ]
    size = widgets["emoji_size"]
    assert isinstance(size, QSpinBox) and (size.minimum(), size.maximum()) == (16, 256)
    assert isinstance(widgets["flip_horizontal"], QToolButton)
    assert isinstance(widgets["shadow_enabled"], QCheckBox)
    preview = next(
        b for b in bar.findChildren(QToolButton) if b.accessibleName() == "Active emoji"
    )
    assert not preview.icon().isNull()
    assert tool._name_label is not None and tool._name_label.text() == "Thumbs up"  # noqa: SLF001
    assert tool._tone_row is not None and not tool._tone_row.isHidden()  # noqa: SLF001
    tool._tone_buttons[SkinTone.LIGHT].click()  # noqa: SLF001
    assert tool.skin_tone is SkinTone.LIGHT
    assert tool.active_char == THUMBS_UP + SKIN_TONE_MODIFIERS[SkinTone.LIGHT]
    tool.set_active_emoji(GRIN)
    assert tool._tone_row.isHidden()  # noqa: SLF001, no tone for a grin
    assert bar.preset_button is not None
    size.setValue(100)
    assert tool.creation_defaults["emoji_size"] == 100


# --- double-click replacement and the context rows (Section 4.6) ---


def test_double_click_opens_the_picker_and_a_pick_is_one_undo_entry(
    main_window: MainWindow,
) -> None:
    _require_font()
    tool = _tool(main_window)
    _click(main_window, QPointF(200, 200))
    (item,) = _emoji(main_window)
    main_window.tool_manager.activate("select")
    _double_click(main_window, QPointF(200, 200))
    picker = tool.picker
    assert isinstance(picker, EmojiPicker) and not picker.isHidden()
    picker.emoji_chosen.emit(DOG)
    assert item.emoji_char == DOG and item.emoji_name == "Dog face"
    main_window.scene.command_stack.undo()
    assert item.emoji_char == THUMBS_UP and item.emoji_name == "Thumbs up"
    main_window.scene.command_stack.redo()
    assert item.emoji_char == DOG
    main_window.tool_manager.activate("emoji")
    _double_click(main_window, QPointF(200, 200))
    assert not picker.isHidden()
    picker.hide()
    _click(main_window, QPointF(200, 200))  # selects, places nothing
    assert len(_emoji(main_window)) == 1
    assert main_window.selection_manager.items == [item]


def test_context_rows_for_one_emoji(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    _require_font()
    _tool(main_window)
    _click(main_window, QPointF(200, 200))
    (item,) = _emoji(main_window)
    main_window.selection_manager.select(item)
    texts = _menu_texts(build_item_context_menu(main_window))
    assert "Change Emoji..." in texts and "Reset Size" in texts
    assert "Flip Horizontal" in texts and "Change Stamp..." not in texts
    item.emoji_size = 120.0
    main_window._emoji_reset_size()  # noqa: SLF001
    assert item.emoji_size == 48.0
    main_window.scene.command_stack.undo()
    assert item.emoji_size == 120.0
    main_window.selection_manager.deselect_all()
    main_window._emoji_reset_size()  # noqa: SLF001
    assert unmet_messages[-1] == ("Reset Size", "Reset Size needs one emoji.")
    main_window._emoji_change()  # noqa: SLF001
    assert unmet_messages[-1] == ("Change Emoji", "Change Emoji needs one emoji.")


def test_change_emoji_command(scene: SnapScene) -> None:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = EmojiItem(THUMBS_UP)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    toned = DOG
    command = ChangeEmojiCommand(item, toned)
    assert command.description == "Change emoji to Dog face"
    assert (command.old_emoji_char, command.new_emoji_char) == (THUMBS_UP, DOG)
    scene.command_stack.push(command)
    assert item.emoji_char == DOG
    scene.command_stack.undo()
    assert item.emoji_char == THUMBS_UP and item.emoji_name == "Thumbs up"


def test_property_panel_shows_an_emoji_section(main_window: MainWindow) -> None:
    _require_font()
    _tool(main_window)
    _click(main_window, QPointF(200, 200))
    (item,) = _emoji(main_window)
    main_window.selection_manager.select(item)
    panel = main_window._property_panel  # noqa: SLF001
    assert not panel._emoji_section.isHidden()  # noqa: SLF001
    assert not panel._shadow_section.isHidden()  # noqa: SLF001
    assert panel._appearance_section.isHidden()  # noqa: SLF001
    assert panel._emoji_name_label.text() == "Thumbs up"  # noqa: SLF001
    panel._emoji_size_spin.setValue(80.0)  # noqa: SLF001
    assert item.emoji_size == 80.0
    combo = panel._emoji_tone_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(SkinTone.DARK))
    assert item.skin_tone is SkinTone.DARK
    assert item.emoji_char.endswith(SKIN_TONE_MODIFIERS[SkinTone.DARK])
    main_window.scene.command_stack.undo()
    assert item.skin_tone is SkinTone.DEFAULT
