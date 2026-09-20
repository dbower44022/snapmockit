"""Tests for menu structure completeness."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from snapmock.main_window import MainWindow


@pytest.fixture()
def window(qtbot: QtBot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _menu_titles(window: MainWindow) -> list[str]:
    """Return the text of all top-level menus."""
    menu_bar = window.menuBar()
    assert menu_bar is not None
    return [a.text() for a in menu_bar.actions() if isinstance(a.menu(), QMenu)]


def test_all_ten_menus_exist(window: MainWindow) -> None:
    titles = _menu_titles(window)
    expected = [
        "&File",
        "&Edit",
        "&View",
        "&Layer",
        "&Image",
        "&Arrange",
        "&Tools",
        "Li&brary",
        "&Capture",
        "&Help",
    ]
    assert titles == expected


def test_tools_menu_has_all_registered_tools(window: MainWindow) -> None:
    """Every registered tool should appear as a checkable action in the Tools menu."""
    tool_ids = window.tool_manager.tool_ids
    assert len(tool_ids) >= 18  # noqa: PLR2004
    # All tool_ids should have a corresponding action
    for tid in tool_ids:
        assert tid in window._tool_actions, f"Tool '{tid}' missing from Tools menu"  # noqa: SLF001


def test_active_tool_is_checked(window: MainWindow) -> None:
    """The currently active tool should be checked in the Tools menu."""
    active_id = window.tool_manager.active_tool_id
    actions = window._tool_actions  # noqa: SLF001
    for tid, action in actions.items():
        if tid == active_id:
            assert action.isChecked(), f"Active tool '{tid}' should be checked"
        else:
            assert not action.isChecked(), f"Inactive tool '{tid}' should not be checked"


def test_tool_check_updates_on_switch(window: MainWindow) -> None:
    """Switching tools should update the checkmark."""
    window.tool_manager.activate("rectangle")
    actions = window._tool_actions  # noqa: SLF001
    assert actions["rectangle"].isChecked()
    assert not actions["select"].isChecked()

    window.tool_manager.activate("select")
    assert actions["select"].isChecked()
    assert not actions["rectangle"].isChecked()


def test_no_menu_action_is_ever_disabled(window: MainWindow) -> None:
    """Never-disabled controls (General UI PRD 1.3): every menu row stays enabled."""
    window.selection_manager.deselect_all()
    assert window.scene.layer_manager.count == 1
    menu_bar = window.menuBar()
    assert menu_bar is not None

    def _walk(menu: QMenu) -> list[str]:
        disabled: list[str] = []
        for action in menu.actions():
            if action.isSeparator():
                continue
            if not action.isEnabled():
                disabled.append(action.text())
            sub = action.menu()
            if isinstance(sub, QMenu):
                disabled.extend(_walk(sub))
        return disabled

    disabled: list[str] = []
    for top in menu_bar.actions():
        sub = top.menu()
        if isinstance(sub, QMenu):
            disabled.extend(_walk(sub))
    assert disabled == []


def test_arrange_actions_explain_unmet_selection(
    window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """With nothing selected, Bring to Front says what it needs instead of graying out."""
    window.selection_manager.deselect_all()
    assert window._bring_front_action is not None  # noqa: SLF001
    assert window._bring_front_action.isEnabled()  # noqa: SLF001
    window._bring_front_action.trigger()  # noqa: SLF001
    assert unmet_messages == [
        ("Bring to Front", "Bring to Front needs at least one item selected.")
    ]


def test_layer_delete_explains_with_single_layer(
    window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """The only layer cannot be deleted; the row says so when triggered."""
    assert window.scene.layer_manager.count == 1
    assert window._layer_delete_action is not None  # noqa: SLF001
    assert window._layer_delete_action.isEnabled()  # noqa: SLF001
    window._layer_delete_action.trigger()  # noqa: SLF001
    assert unmet_messages == [("Delete Layer", "Delete Layer needs more than one layer.")]
    assert window.scene.layer_manager.count == 1


def test_recent_files_placeholder_explains(
    window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    assert window._recent_menu is not None  # noqa: SLF001
    rows = [a for a in window._recent_menu.actions() if not a.isSeparator()]  # noqa: SLF001
    assert len(rows) == 1
    assert rows[0].isEnabled()
    rows[0].trigger()
    assert unmet_messages == [("Open Recent", "Open Recent needs a recently opened file.")]


def _menu(window: MainWindow, title: str) -> QMenu:
    menu_bar = window.menuBar()
    assert menu_bar is not None
    for action in menu_bar.actions():
        if action.text() == title and isinstance(action.menu(), QMenu):
            return action.menu()  # type: ignore[return-value]
    raise AssertionError(title)


def _texts(menu: QMenu) -> list[str]:
    return [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]


def test_file_menu_order_and_open_recent(window: MainWindow) -> None:
    texts = _texts(_menu(window, "&File"))
    assert texts.index("Open...") < texts.index("Open Recent") < texts.index("Close")
    assert "Export Quick (PNG)" in texts
    assert window._recent_menu is not None  # noqa: SLF001
    window._add_recent_file(Path("/tmp/example.smk"))  # noqa: SLF001
    recent = _texts(window._recent_menu)  # noqa: SLF001
    assert recent == ["example.smk", "Clear Recent"]
    window._clear_recent_files()  # noqa: SLF001
    assert _texts(window._recent_menu) == ["(No recent files)"]  # noqa: SLF001


def test_undo_redo_show_the_action_name(window: MainWindow) -> None:
    from PyQt6.QtCore import QRectF

    from snapmock.commands.add_item import AddItemCommand
    from snapmock.items.rectangle_item import RectangleItem

    assert window._undo_action.text() == "&Undo"  # noqa: SLF001
    layer = window.scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 10, 10))
    window.scene.command_stack.push(AddItemCommand(window.scene, item, layer.layer_id))
    assert window._undo_action.text().startswith("&Undo ")  # noqa: SLF001
    assert window._undo_action.text() != "&Undo"  # noqa: SLF001
    window.scene.command_stack.undo()
    assert window._redo_action.text().startswith("&Redo ")  # noqa: SLF001
    window.scene.command_stack.mark_clean()


def test_view_menu_labels_and_status_bar_toggle(window: MainWindow) -> None:
    texts = _texts(_menu(window, "&View"))
    for label in (
        "Zoom to 100%",
        "Show Grid",
        "Snap to Grid",
        "Show Rulers",
        "Show Crosshairs",
        "Show Guides",
        "Snap to Guides",
        "Lock Guides",
        "Clear All Guides",
        "Show Tool Palette",
        "Show Tool Options",
        "Show Layer Panel",
        "Show Property Panel",
        "Show Status Bar",
    ):
        assert label in texts, label
    assert texts.index("Snap to Grid") < texts.index("Show Rulers")
    assert texts.index("Show Rulers") < texts.index("Show Crosshairs")
    assert texts.index("Show Crosshairs") < texts.index("Show Guides")
    assert texts.index("Show Guides") < texts.index("Snap to Guides")
    assert texts.index("Snap to Guides") < texts.index("Lock Guides")
    assert texts.index("Lock Guides") < texts.index("Clear All Guides")
    assert texts.index("Clear All Guides") < texts.index("Show Main Toolbar")
    window._status_bar_action.setChecked(False)  # noqa: SLF001
    assert not window.statusBar().isVisibleTo(window)  # type: ignore[union-attr]
    window._status_bar_action.setChecked(True)  # noqa: SLF001
    assert window.statusBar().isVisibleTo(window)  # type: ignore[union-attr]


def test_arrange_menu_order_and_group_rows(
    window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    texts = _texts(_menu(window, "&Arrange"))
    assert texts.index("Send to Back") < texts.index("Align") < texts.index("Distribute")
    assert texts.index("Align to Canvas Center") < texts.index("Group") < texts.index("Ungroup")
    assert texts.index("Ungroup") < texts.index("Flip Horizontal")
    for action in _menu(window, "&Arrange").actions():
        if action.text() == "&Group":
            assert action.shortcut().toString() == "Ctrl+G"
            action.trigger()
    assert unmet_messages == [("Group", "Group needs at least two items selected.")]


def test_help_menu_order_and_links(window: MainWindow) -> None:
    from snapmock.config.constants import DOCUMENTATION_URL, ISSUES_URL

    texts = _texts(_menu(window, "&Help"))
    # The fifth row reads Add to Menu, or Remove from Menu where this machine
    # already has the entry (menu-entry decision 1), so the label is read as
    # either rather than fixed to the developer's own desktop.
    assert texts[4] in {"Add to Menu", "Remove from Menu"}
    assert texts[:4] + texts[5:] == [
        "Welcome / Getting Started",
        "Documentation",
        "Keyboard Shortcuts",
        "Report a Bug",
        "Check for Updates",
        "About Snapmockit",
    ]
    assert DOCUMENTATION_URL.startswith("https://github.com/dbower44022/snapmockit")
    assert ISSUES_URL == "https://github.com/dbower44022/snapmockit/issues"


def test_delete_row_has_backspace_alternate(window: MainWindow) -> None:
    for action in _menu(window, "&Edit").actions():
        if action.text() == "&Delete":
            keys = [k.toString() for k in action.shortcuts()]
            assert keys == ["Del", "Backspace"]
            return
    raise AssertionError("Delete row not found")
