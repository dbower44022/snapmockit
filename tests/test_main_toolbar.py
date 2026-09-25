"""The Main Toolbar of General UI PRD Section 4 and its zoom dropdown."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QToolButton
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.document import Document
from snapmock.core.scene import SnapScene
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.ui.icons import plain_label
from snapmock.ui.toolbar import (
    MAIN_TOOLBAR_BUTTON_SIZE,
    MAIN_TOOLBAR_HEIGHT,
    ZOOM_PRESETS,
    MainToolBar,
    ZoomDropdown,
    action_tooltip,
)


def _groups(bar: MainToolBar) -> list[list[str]]:
    """Button labels per group, split on separators; widget-only entries are named."""
    groups: list[list[str]] = [[]]
    for action in bar.actions():
        if action.isSeparator():
            groups.append([])
            continue
        widget = bar.widgetForAction(action)
        if isinstance(widget, ZoomDropdown):
            groups[-1].append("<zoom>")
        elif isinstance(widget, QToolButton) and not action.text():
            groups[-1].append(widget.text())
        else:
            groups[-1].append(plain_label(action.text()))
    return groups


def _add_rects(window: MainWindow, count: int) -> list[RectangleItem]:
    scene = window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    items = []
    for i in range(count):
        item = RectangleItem(rect=QRectF(0, 0, 20, 10))
        item.setPos(i * 40, 0)
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        items.append(item)
    return items


def test_groups_in_prd_order_with_dividers(main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    assert _groups(bar) == [
        ["Capture"],
        ["New", "Open...", "Save", "Export Quick (PNG)"],
        ["Undo", "Redo", "Cut", "Copy", "Paste"],
        ["Duplicate", "Delete"],
        ["Bring to Front", "Send to Back"],
        [
            "Align Left",
            "Align Center (H)",
            "Align Right",
            "Align Top",
            "Align Middle (V)",
            "Align Bottom",
        ],
        ["Zoom Out", "<zoom>", "Zoom In", "Fit to Window"],
    ]


def test_placement_below_the_menu_bar_and_object_name(main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    assert bar.objectName() == "MainToolBar"
    assert main_window.toolBarArea(bar) == Qt.ToolBarArea.TopToolBarArea
    assert not bar.isMovable()
    assert bar.height() == MAIN_TOOLBAR_HEIGHT
    assert bar.iconSize().width() == 24


def test_buttons_are_icon_only_with_shortcut_tooltips(main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    seen = 0
    for action in bar.actions():
        widget = bar.widgetForAction(action)
        if action.isSeparator() or not action.text() or not isinstance(widget, QToolButton):
            continue
        assert not action.icon().isNull(), action.text()
        # A hidden QAction reports itself disabled; the Align copies start hidden (PRD 4.2).
        assert action.isEnabled() or action in bar.alignment_actions, action.text()
        assert widget.size().width() == MAIN_TOOLBAR_BUTTON_SIZE
        assert widget.size().height() == MAIN_TOOLBAR_BUTTON_SIZE
        seen += 1
    assert seen == 22
    save = main_window._actions["file.save"]  # noqa: SLF001
    assert save.toolTip() == "Save (Ctrl+S)"
    assert main_window._actions["view.zoom_out"].toolTip() == "Zoom Out (Ctrl+-)"  # noqa: SLF001
    align_left = main_window._main_toolbar.alignment_actions[0]  # noqa: SLF001
    assert align_left.toolTip() == "Align Left"


def test_action_tooltip_drops_ellipsis() -> None:
    action = QAction("&Open...")
    action.setShortcut("Ctrl+O")
    assert action_tooltip(action) == "Open (Ctrl+O)"


def test_toolbar_button_shows_unmet_requirement(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    main_window._actions["edit.delete"].trigger()  # noqa: SLF001
    assert unmet_messages and unmet_messages[0][0] == "Delete"


def test_alignment_group_shown_with_two_or_more_selected(main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    align = bar.alignment_actions
    assert len(align) == 6
    assert not any(a.isVisible() for a in align)
    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items([items[0]])
    assert not any(a.isVisible() for a in align)
    main_window.selection_manager.select_items(items)
    assert all(a.isVisible() for a in align)
    main_window.selection_manager.deselect_all()
    assert not any(a.isVisible() for a in align)


def test_zoom_dropdown_presets_and_sync(main_window: MainWindow) -> None:
    dropdown = main_window._main_toolbar.zoom_dropdown  # noqa: SLF001
    assert dropdown is not None
    assert [dropdown.itemData(i) for i in range(dropdown.count())] == list(ZOOM_PRESETS)
    assert dropdown.currentText() == "100%"
    main_window.view.set_zoom(200)
    assert dropdown.currentText() == "200%"
    main_window.view.set_zoom(33)
    assert dropdown.currentText() == "33%"
    dropdown.setCurrentIndex(dropdown.findText("400%"))
    assert main_window.view.zoom_percent == 400


def test_zoom_dropdown_custom_entry_and_range_message(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    dropdown = main_window._main_toolbar.zoom_dropdown  # noqa: SLF001
    assert dropdown is not None
    dropdown.setEditText("137%")
    dropdown._on_custom_entry()  # noqa: SLF001
    assert main_window.view.zoom_percent == 137
    dropdown.setEditText("5000")
    dropdown._on_custom_entry()  # noqa: SLF001
    assert main_window.view.zoom_percent == 137
    assert unmet_messages[-1] == ("Zoom", "Zoom needs a whole number between 10% and 3200%.")
    assert dropdown.currentText() == "137%"


def test_zoom_dropdown_follows_the_active_tab(main_window: MainWindow) -> None:
    dropdown = main_window._main_toolbar.zoom_dropdown  # noqa: SLF001
    assert dropdown is not None
    _add_rects(main_window, 1)  # not pristine, so the second document does not replace it
    main_window.view.set_zoom(150)
    second = Document(SnapScene(), parent=main_window)
    main_window._add_document(second)  # noqa: SLF001
    assert main_window.active_document is second
    assert dropdown.snap_view is second.view
    assert dropdown.currentText() == "100%"
    second.view.set_zoom(50)
    assert dropdown.currentText() == "50%"
    main_window.documents.set_active_index(0)
    assert dropdown.currentText() == "150%"


def test_alignment_visibility_follows_the_active_tab(main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items(items)
    assert all(a.isVisible() for a in bar.alignment_actions)
    second = Document(SnapScene(), parent=main_window)
    main_window._add_document(second)  # noqa: SLF001
    assert not any(a.isVisible() for a in bar.alignment_actions)
    main_window.documents.set_active_index(0)
    assert all(a.isVisible() for a in bar.alignment_actions)


def test_view_menu_toggle_and_reset_layout(qtbot: QtBot, main_window: MainWindow) -> None:
    bar = main_window._main_toolbar  # noqa: SLF001
    main_window.show()
    qtbot.waitExposed(main_window)
    QApplication.processEvents()
    menu_bar = main_window.menuBar()
    assert menu_bar is not None
    view_menu = next(a.menu() for a in menu_bar.actions() if a.text() == "&View")
    assert view_menu is not None
    labels = [plain_label(a.text()) for a in view_menu.actions() if not a.isSeparator()]
    assert labels.index("Show Main Toolbar") < labels.index("Show Tool Palette")
    toggle = next(a for a in view_menu.actions() if plain_label(a.text()) == "Show Main Toolbar")
    assert toggle.isChecked()
    toggle.trigger()
    assert bar.isHidden()
    main_window._view_reset_layout()  # noqa: SLF001
    assert bar.isVisibleTo(main_window)
    assert main_window.toolBarArea(bar) == Qt.ToolBarArea.TopToolBarArea


def test_tool_palette_is_a_vertical_left_column(main_window: MainWindow) -> None:
    palette = main_window._toolbar  # noqa: SLF001
    assert main_window.toolBarArea(palette) == Qt.ToolBarArea.LeftToolBarArea
    assert palette.orientation() == Qt.Orientation.Vertical
    assert palette.width() == 48
    assert not palette.isMovable()
    for tool_id, button in palette._buttons.items():  # noqa: SLF001
        assert button.size().width() == 32 and button.size().height() == 32, tool_id
    assert len(palette._buttons) == 22  # noqa: SLF001, twenty-two since the Border tool


def test_tool_palette_toggle_keeps_working(main_window: MainWindow) -> None:
    palette = main_window._toolbar  # noqa: SLF001
    menu_bar = main_window.menuBar()
    assert menu_bar is not None
    view_menu = next(a.menu() for a in menu_bar.actions() if a.text() == "&View")
    assert view_menu is not None
    toggle = next(a for a in view_menu.actions() if plain_label(a.text()) == "Show Tool Palette")
    assert toggle is palette.toggleViewAction()
    palette.hide()
    main_window._view_reset_layout()  # noqa: SLF001
    assert palette.isVisibleTo(main_window)
    assert main_window.toolBarArea(palette) == Qt.ToolBarArea.LeftToolBarArea
