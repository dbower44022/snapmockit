"""Tests for context menus and MoveItemToLayerCommand."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from snapmock.commands.move_item_layer import MoveItemToLayerCommand
from snapmock.core.scene import SnapScene
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.ui.context_menus import (
    build_canvas_context_menu,
    build_item_context_menu,
    build_layer_panel_context_menu,
)


def _make_rect(
    scene: SnapScene, x: float, y: float, w: float = 50, h: float = 50
) -> RectangleItem:
    """Create a rectangle item at (x, y) and add to the scene's active layer."""
    item = RectangleItem(rect=QRectF(0, 0, w, h))
    item.setPos(x, y)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.addItem(item)
    item.layer_id = layer.layer_id
    layer.item_ids.append(item.item_id)
    return item


@pytest.fixture()
def window(qtbot: QtBot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _action_texts(menu: QMenu) -> list[str]:
    """Return all non-separator action texts, including submenu titles."""
    texts: list[str] = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        texts.append(action.text())
    return texts


# ---- Canvas context menu ----


class TestCanvasContextMenu:
    def test_has_expected_actions(self, window: MainWindow) -> None:
        menu = build_canvas_context_menu(window)
        texts = _action_texts(menu)
        assert "Paste" in texts
        assert "Paste in Place" in texts
        assert "Select All" in texts
        assert "Canvas Properties..." in texts
        assert "Zoom In" in texts
        assert "Zoom Out" in texts
        assert "Fit to Window" in texts
        assert "Zoom to 100%" in texts

    def test_paste_never_disabled_and_explains_when_clipboard_empty(
        self, window: MainWindow, unmet_messages: list[tuple[str, str]]
    ) -> None:
        from PyQt6.QtWidgets import QApplication

        window.clipboard.clear()
        # Also clear the system clipboard to avoid false positives
        sys_cb = QApplication.clipboard()
        if sys_cb is not None:
            sys_cb.clear()
        menu = build_canvas_context_menu(window)
        for action in menu.actions():
            if action.text() == "Paste":
                assert action.isEnabled()
                action.trigger()
                break
        else:
            pytest.fail("Paste action not found")
        assert unmet_messages == [("Paste", "Paste needs content on the clipboard.")]

    def test_paste_enabled_when_clipboard_has_items(self, window: MainWindow) -> None:
        # Copy an item to fill the clipboard
        item = _make_rect(window.scene, 0, 0)
        window.clipboard.copy_items([item])
        menu = build_canvas_context_menu(window)
        for action in menu.actions():
            if action.text() == "Paste":
                assert action.isEnabled()
                break
        else:
            pytest.fail("Paste action not found")


# ---- Item context menu ----


class TestItemContextMenu:
    def test_has_expected_actions(self, window: MainWindow) -> None:
        item = _make_rect(window.scene, 10, 10)
        window.selection_manager.select(item)
        menu = build_item_context_menu(window)
        texts = _action_texts(menu)
        assert "Cut" in texts
        assert "Copy" in texts
        assert "Paste" in texts
        assert "Duplicate" in texts
        assert "Delete" in texts
        assert "Bring to Front" in texts
        assert "Bring Forward" in texts
        assert "Send Backward" in texts
        assert "Send to Back" in texts
        assert "Move to Layer" in texts
        assert "Align" in texts
        assert "Distribute" in texts
        assert "Properties..." in texts

    def test_lock_text_shows_lock_item(self, window: MainWindow) -> None:
        item = _make_rect(window.scene, 10, 10)
        item.locked = False
        window.selection_manager.select(item)
        menu = build_item_context_menu(window)
        texts = _action_texts(menu)
        assert "Lock Item" in texts

    def test_lock_text_shows_unlock_item(self, window: MainWindow) -> None:
        item = _make_rect(window.scene, 10, 10)
        item.locked = True
        window.selection_manager.select(item)
        menu = build_item_context_menu(window)
        texts = _action_texts(menu)
        assert "Unlock Item" in texts

    def test_align_never_disabled_and_explains_with_single_selection(
        self, window: MainWindow, unmet_messages: list[tuple[str, str]]
    ) -> None:
        item = _make_rect(window.scene, 10, 10)
        window.selection_manager.select(item)
        menu = build_item_context_menu(window)
        for action in menu.actions():
            sub = action.menu()
            if isinstance(sub, QMenu) and action.text() == "Align":
                assert sub.isEnabled()
                sub.actions()[0].trigger()
                break
        else:
            pytest.fail("Align submenu not found")
        assert unmet_messages == [("Align", "Align needs at least two items selected.")]

    def test_align_enabled_with_two_items(self, window: MainWindow) -> None:
        a = _make_rect(window.scene, 10, 10)
        b = _make_rect(window.scene, 50, 50)
        window.selection_manager.select(a)
        window.selection_manager.select(b, add=True)
        menu = build_item_context_menu(window)
        for action in menu.actions():
            sub = action.menu()
            if isinstance(sub, QMenu) and action.text() == "Align":
                assert sub.isEnabled()
                break
        else:
            pytest.fail("Align submenu not found")

    def test_distribute_never_disabled_and_explains_with_two_items(
        self, window: MainWindow, unmet_messages: list[tuple[str, str]]
    ) -> None:
        a = _make_rect(window.scene, 10, 10)
        b = _make_rect(window.scene, 50, 50)
        window.selection_manager.select(a)
        window.selection_manager.select(b, add=True)
        menu = build_item_context_menu(window)
        for action in menu.actions():
            sub = action.menu()
            if isinstance(sub, QMenu) and action.text() == "Distribute":
                assert sub.isEnabled()
                sub.actions()[0].trigger()
                break
        else:
            pytest.fail("Distribute submenu not found")
        assert unmet_messages == [("Distribute", "Distribute needs at least 3 items selected.")]

    def test_distribute_enabled_with_three_items(self, window: MainWindow) -> None:
        a = _make_rect(window.scene, 10, 10)
        b = _make_rect(window.scene, 50, 50)
        c = _make_rect(window.scene, 100, 100)
        window.selection_manager.select(a)
        window.selection_manager.select(b, add=True)
        window.selection_manager.select(c, add=True)
        menu = build_item_context_menu(window)
        for action in menu.actions():
            sub = action.menu()
            if isinstance(sub, QMenu) and action.text() == "Distribute":
                assert sub.isEnabled()
                break
        else:
            pytest.fail("Distribute submenu not found")

    def test_move_to_layer_lists_all_layers(self, window: MainWindow) -> None:
        window.scene.layer_manager.add_layer("Layer 2")
        item = _make_rect(window.scene, 10, 10)
        window.selection_manager.select(item)
        menu = build_item_context_menu(window)
        for action in menu.actions():
            sub = action.menu()
            if isinstance(sub, QMenu) and action.text() == "Move to Layer":
                layer_names = [a.text() for a in sub.actions()]
                assert len(layer_names) == 2  # noqa: PLR2004
                break
        else:
            pytest.fail("Move to Layer submenu not found")


# ---- Layer panel context menu ----


class TestLayerPanelContextMenu:
    def test_has_expected_actions(self, window: MainWindow) -> None:
        lm = window.scene.layer_manager
        layer = lm.active_layer
        assert layer is not None
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        texts = _action_texts(menu)
        assert "New Layer Above" in texts
        assert "New Layer Below" in texts
        assert "Duplicate Layer" in texts
        assert "Delete Layer" in texts
        assert "Rename Layer" in texts
        assert "Merge Down" in texts
        assert "Merge Visible" in texts
        assert "Flatten All" in texts
        assert "Layer Properties..." in texts

    def test_delete_never_disabled_and_explains_with_single_layer(
        self, window: MainWindow, unmet_messages: list[tuple[str, str]]
    ) -> None:
        lm = window.scene.layer_manager
        assert lm.count == 1
        layer = lm.active_layer
        assert layer is not None
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        for action in menu.actions():
            if action.text() == "Delete Layer":
                assert action.isEnabled()
                action.trigger()
                break
        else:
            pytest.fail("Delete Layer action not found")
        assert unmet_messages == [("Delete Layer", "Delete Layer needs more than one layer.")]
        assert lm.count == 1

    def test_delete_enabled_with_multiple_layers(self, window: MainWindow) -> None:
        lm = window.scene.layer_manager
        lm.add_layer("Layer 2")
        layer = lm.active_layer
        assert layer is not None
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        for action in menu.actions():
            if action.text() == "Delete Layer":
                assert action.isEnabled()
                break
        else:
            pytest.fail("Delete Layer action not found")

    def test_merge_down_never_disabled_and_explains_for_bottom_layer(
        self, window: MainWindow, unmet_messages: list[tuple[str, str]]
    ) -> None:
        lm = window.scene.layer_manager
        lm.add_layer("Layer 2")
        # Bottom layer is at index 0
        bottom_layer = lm.layers[0]
        lm.set_active(bottom_layer.layer_id)
        menu = build_layer_panel_context_menu(window, lm, bottom_layer.layer_id)
        for action in menu.actions():
            if action.text() == "Merge Down":
                assert action.isEnabled()
                action.trigger()
                break
        else:
            pytest.fail("Merge Down action not found")
        assert unmet_messages == [
            ("Merge Down", "Merge Down needs a layer below the active layer.")
        ]

    def test_merge_down_enabled_for_non_bottom_layer(self, window: MainWindow) -> None:
        lm = window.scene.layer_manager
        lm.add_layer("Layer 2")
        top_layer = lm.layers[-1]
        menu = build_layer_panel_context_menu(window, lm, top_layer.layer_id)
        for action in menu.actions():
            if action.text() == "Merge Down":
                assert action.isEnabled()
                break
        else:
            pytest.fail("Merge Down action not found")

    def test_lock_text_toggles(self, window: MainWindow) -> None:
        lm = window.scene.layer_manager
        layer = lm.active_layer
        assert layer is not None
        # Unlocked by default
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        texts = _action_texts(menu)
        assert "Lock Layer" in texts

        # Lock it
        lm.set_locked(layer.layer_id, True)
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        texts = _action_texts(menu)
        assert "Unlock Layer" in texts

    def test_visibility_text_toggles(self, window: MainWindow) -> None:
        lm = window.scene.layer_manager
        layer = lm.active_layer
        assert layer is not None
        # Visible by default
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        texts = _action_texts(menu)
        assert "Hide Layer" in texts

        # Hide it
        lm.set_visibility(layer.layer_id, False)
        menu = build_layer_panel_context_menu(window, lm, layer.layer_id)
        texts = _action_texts(menu)
        assert "Show Layer" in texts


# ---- MoveItemToLayerCommand ----


class TestMoveItemToLayerCommand:
    def test_move_item_to_another_layer(self) -> None:
        scene = SnapScene()
        lm = scene.layer_manager
        layer1 = lm.active_layer
        assert layer1 is not None
        layer2 = lm.add_layer("Layer 2")

        item = _make_rect(scene, 10, 10)
        assert item.layer_id == layer1.layer_id
        assert item.item_id in layer1.item_ids

        cmd = MoveItemToLayerCommand(scene, [item], layer2.layer_id)
        cmd.redo()

        assert item.layer_id == layer2.layer_id
        assert item.item_id in layer2.item_ids
        assert item.item_id not in layer1.item_ids

    def test_undo_restores_original_layer(self) -> None:
        scene = SnapScene()
        lm = scene.layer_manager
        layer1 = lm.active_layer
        assert layer1 is not None
        layer2 = lm.add_layer("Layer 2")

        item = _make_rect(scene, 10, 10)
        original_id = item.layer_id

        cmd = MoveItemToLayerCommand(scene, [item], layer2.layer_id)
        cmd.redo()
        cmd.undo()

        assert item.layer_id == original_id
        assert item.item_id in layer1.item_ids
        assert item.item_id not in layer2.item_ids

    def test_move_multiple_items(self) -> None:
        scene = SnapScene()
        lm = scene.layer_manager
        layer1 = lm.active_layer
        assert layer1 is not None
        layer2 = lm.add_layer("Layer 2")

        a = _make_rect(scene, 0, 0)
        b = _make_rect(scene, 50, 50)

        cmd = MoveItemToLayerCommand(scene, [a, b], layer2.layer_id)
        cmd.redo()

        assert a.layer_id == layer2.layer_id
        assert b.layer_id == layer2.layer_id
        assert a.item_id in layer2.item_ids
        assert b.item_id in layer2.item_ids
        assert a.item_id not in layer1.item_ids
        assert b.item_id not in layer1.item_ids

    def test_description(self) -> None:
        scene = SnapScene()
        lm = scene.layer_manager
        layer2 = lm.add_layer("Layer 2")
        item = _make_rect(scene, 0, 0)
        cmd = MoveItemToLayerCommand(scene, [item], layer2.layer_id)
        assert cmd.description == "Move to layer"


# ---- Regression: context menu through the view inside the tab stack ----


class TestContextMenuThroughView:
    def test_select_tool_resolves_main_window_from_view(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Right-click on the canvas must find the MainWindow, not the tab stack.

        The view's direct parent is a QStackedWidget since the tab work landed; the
        select tool must walk up to the window before building the menu.
        """
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QContextMenuEvent

        from snapmock.tools import select_tool as select_tool_module

        window.tool_manager.activate("select")
        captured: list[object] = []

        def fake_canvas_menu(parent: object, *_args: object) -> QMenu:
            captured.append(parent)
            return QMenu()

        monkeypatch.setattr(
            "snapmock.ui.context_menus.build_canvas_context_menu", fake_canvas_menu
        )
        monkeypatch.setattr(QMenu, "exec", lambda self, *_a, **_k: None)

        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, QPoint(5, 5), window.view.mapToGlobal(QPoint(5, 5))
        )
        tool = window.tool_manager.active_tool
        assert isinstance(tool, select_tool_module.SelectTool)
        assert tool.context_menu(event) is True
        assert captured == [window]
