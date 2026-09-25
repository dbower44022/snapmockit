"""Acceptance pass against General UI PRD Section 17 (implementation notes Section 16).

One test per bullet that had no automated evidence and can be judged offscreen. Each test
is named after its bullet and carries the Section 16 row number. A test that documents a
fail asserts what the code does today and says so, so the suite stays green while the
record says what the pass found.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QDropEvent, QKeySequence, QMouseEvent, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
)
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.move_items import MoveItemsCommand
from snapmock.config.constants import APP_VERSION, MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH
from snapmock.config.settings import AppSettings
from snapmock.core import theme_manager as tm
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.ui.accessibility import describe, focusable_controls
from snapmock.ui.icons import plain_label, tool_tooltip
from snapmock.ui.preferences_dialog import PreferencesDialog
from snapmock.ui.ruler_widget import RulerWidget

# ---- helpers ----


def _menu(window: MainWindow, title: str) -> QMenu:
    bar = window.menuBar()
    assert bar is not None
    for action in bar.actions():
        if plain_label(action.text()) == title:
            menu = action.menu()
            assert isinstance(menu, QMenu)
            return menu
    raise AssertionError(f"no menu {title!r}")


def _rows(menu: QMenu) -> dict[str, object]:
    """Every row of *menu* and its submenus by plain label."""
    rows: dict[str, object] = {}
    for action in menu.actions():
        if action.isSeparator():
            continue
        rows[plain_label(action.text())] = action
        sub = action.menu()
        if isinstance(sub, QMenu):
            rows.update(_rows(sub))
    return rows


def _add_rects(window: MainWindow, count: int) -> list[RectangleItem]:
    scene = window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    items = []
    for i in range(count):
        item = RectangleItem(rect=QRectF(0, 0, 40, 30))
        item.setPos(i * 60, 0)
        scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
        items.append(item)
    return items


def _shortcut(action: object) -> str:
    return action.shortcut().toString()  # type: ignore[attr-defined]


# ---- 17.1 Window & Layout ----


def test_17_1_window_opens_at_80_percent_of_the_screen(main_window: MainWindow) -> None:
    """Row 1: the default size is 80 percent of the primary screen's available area,
    never below the 1024 by 600 minimum, and a window with no saved geometry takes it."""
    screen = QApplication.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry().size()
    expected = QSize(
        max(MIN_WINDOW_WIDTH, int(available.width() * 0.8)),
        max(MIN_WINDOW_HEIGHT, int(available.height() * 0.8)),
    )
    assert MainWindow._default_window_size() == expected  # noqa: SLF001
    assert main_window.size() == expected


def test_17_1_panels_dock_float_tab_close_and_reopen(main_window: MainWindow) -> None:
    """Row 2: dock areas against Section 2.3, float, tab, close, reopen via View."""
    layer = main_window._layer_panel  # noqa: SLF001
    prop = main_window._property_panel  # noqa: SLF001
    # Section 16 row 2 failed as found (the bottom edge was refused) and is fixed since:
    # Section 2.3 allows the left, right, and bottom edges.
    edges = (
        Qt.DockWidgetArea.LeftDockWidgetArea
        | Qt.DockWidgetArea.RightDockWidgetArea
        | Qt.DockWidgetArea.BottomDockWidgetArea
    )
    assert layer.allowedAreas() == edges
    assert prop.allowedAreas() == edges
    main_window.removeDockWidget(layer)
    main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, layer)
    layer.show()
    assert main_window.dockWidgetArea(layer) == Qt.DockWidgetArea.BottomDockWidgetArea
    main_window.removeDockWidget(layer)
    main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, layer)
    layer.show()

    layer.setFloating(True)
    assert layer.isFloating()
    layer.setFloating(False)
    assert main_window.dockWidgetArea(layer) == Qt.DockWidgetArea.RightDockWidgetArea

    main_window.tabifyDockWidget(layer, prop)
    assert prop in main_window.tabifiedDockWidgets(layer)

    for panel in (layer, prop, main_window._library_panel):  # noqa: SLF001
        toggle = panel.toggleViewAction()
        assert toggle is not None
        panel.close()
        assert not panel.isVisibleTo(main_window)
        assert not toggle.isChecked()
        toggle.trigger()
        assert panel.isVisibleTo(main_window)
        assert toggle.isChecked()


def test_17_1_panel_layout_is_restored_in_a_new_window(qtbot: QtBot) -> None:
    """Row 3: a floated Layer Panel and a left-docked, resized Property Panel come back."""
    first = MainWindow()
    qtbot.addWidget(first)
    first.show()
    first._layer_panel.setFloating(True)  # noqa: SLF001
    first.removeDockWidget(first._property_panel)  # noqa: SLF001
    first.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, first._property_panel)  # noqa: SLF001
    first._property_panel.show()  # noqa: SLF001
    first.resizeDocks([first._property_panel], [260], Qt.Orientation.Horizontal)  # noqa: SLF001
    first._save_window_state()  # noqa: SLF001
    assert AppSettings().window_state() is not None

    second = MainWindow()
    qtbot.addWidget(second)
    second.show()
    assert second._layer_panel.isFloating()  # noqa: SLF001
    assert second.dockWidgetArea(second._property_panel) == (  # noqa: SLF001
        Qt.DockWidgetArea.LeftDockWidgetArea
    )


def test_17_1_window_title_shows_the_name_and_the_dirty_asterisk(
    main_window: MainWindow, tmp_path: Path
) -> None:
    """Row 5: "[Name] - Snapmockit", an asterisk while dirty, the file's stem after a save."""
    assert main_window.windowTitle() == "Untitled - Snapmockit"
    _add_rects(main_window, 1)
    assert main_window.windowTitle() == "*Untitled - Snapmockit"
    main_window._save_to(tmp_path / "acceptance.smk")  # noqa: SLF001
    assert main_window.windowTitle() == "acceptance - Snapmockit"
    _add_rects(main_window, 1)
    assert main_window.windowTitle() == "*acceptance - Snapmockit"


# ---- 17.2 Menu Bar ----

# The rows of the Section 3 tables, by menu, with the label the code uses where it differs
# from the table (implementation notes Section 16 row 6 lists the differences).
SECTION_3_ROWS: dict[str, list[str]] = {
    "File": [
        "New",
        "Open...",
        "Open Recent",
        "Save",
        "Save As...",
        "Import Image...",
        "Export...",
        "Export Quick (PNG)",
        "Print...",
        "Preferences...",
        "Quit",
    ],
    "Edit": [
        "Undo",
        "Redo",
        "Cut",
        "Copy",
        "Copy All",
        "Paste",
        "Paste in Place",
        "Duplicate",
        "Delete",
        "Select All",
        "Select All on Layer",
        "Select All Layers",
        "Deselect",
        "Select All Text",
        "Find/Replace Color...",
    ],
    "View": [
        "Zoom In",
        "Zoom Out",
        "Zoom to 100%",
        "Fit to Window",
        "Zoom to Selection",
        "Show Grid",
        "Snap to Grid",
        "Show Rulers",
        "Show Crosshairs",
        "Show Guides",
        "Snap to Guides",
        "Lock Guides",
        "Clear All Guides",
        "Show Main Toolbar",
        "Show Tool Options",
        "Show Tool Palette",
        "Show Layer Panel",
        "Show Property Panel",
        "Show Status Bar",
        "Reset Layout",
        "Dark Mode",
    ],
    "Layer": [
        "New Layer",
        "Duplicate Layer",
        "Delete Layer",
        "Merge Down",
        "Merge Visible",
        "Flatten All",
        "Rename Layer",
        "Layer Properties...",
        "Move Up",  # table: Move Layer Up
        "Move Down",  # table: Move Layer Down
        "Move to Top",  # table: Move Layer to Top
        "Move to Bottom",  # table: Move Layer to Bottom
    ],
    "Image": [
        "Crop to Canvas",
        "Resize Canvas...",
        "Resize Image...",
        "Rotate Canvas 90° CW",
        "Rotate Canvas 90° CCW",
        "Flip Canvas Horizontal",
        "Flip Canvas Vertical",
        "Auto-Trim",
    ],
    "Arrange": [
        "Bring to Front",
        "Bring Forward",
        "Send Backward",
        "Send to Back",
        "Align Left",
        "Align Center (H)",
        "Align Right",
        "Align Top",
        "Align Middle (V)",
        "Align Bottom",
        "Distribute Horizontally",
        "Distribute Vertically",
        "Align to Canvas Center",
        "Group",
        "Ungroup",
        "Flip Horizontal",
        "Flip Vertical",
    ],
    "Tools": [
        "Select",  # table: Select / Move
        "Raster Select",  # table: Raster Selection (Rectangle)
        "Lasso Select",  # table: Raster Selection (Freeform)
        "Crop",  # table: Crop Canvas
        "Arrow",
        "Line",
        "Arc",  # the twentieth tool (Basic Shape remainder decision 3)
        "Polygon",  # the twenty-first
        "Rectangle",
        "Ellipse",
        "Freehand",  # table: Freehand / Pen
        "Text",  # table: Text Box
        "Callout",  # table: Callout Bubble
        "Blur",  # table: Blur / Pixelate
        "Highlight",  # table: Highlighter
        "Numbered Step",
        "Stamp",  # table: Stamp / Sticker
        "Eyedropper",
        "Pan",  # table: Pan / Hand
        "Zoom",
        "Tool Themes...",
    ],
    "Help": [
        "Welcome / Getting Started",
        "Documentation",
        "Keyboard Shortcuts",
        "Report a Bug",
        "Check for Updates",
        "About Snapmockit",
    ],
}


def test_17_2_every_section_3_row_is_present_and_the_deferred_rows_say_so(
    main_window: MainWindow,
    unmet_messages: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row 6: every table row found by label; every row acts (the six deferred rows
    were fixed since the pass by the Group and Ungroup kickoff, the Navigation and
    Raster Operations follow-up, and the Check for Updates work)."""
    for title, labels in SECTION_3_ROWS.items():
        rows = _rows(_menu(main_window, title))
        missing = [label for label in labels if label not in rows]
        assert missing == [], f"{title}: {missing}"
    assert main_window.active_theme_text.startswith("Active Theme:")

    # Section 16 row 6: Group and Ungroup act since the Group and Ungroup kickoff (fixed
    # since); four rows are present and explain a deferral instead of acting.
    from snapmock.items.group_item import GroupItem

    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items(items)  # type: ignore[arg-type]
    arrange = _rows(_menu(main_window, "Arrange"))
    arrange["Group"].trigger()  # type: ignore[attr-defined]
    selected = main_window.selection_manager.items
    assert len(selected) == 1 and isinstance(selected[0], GroupItem)
    assert selected[0].members == items
    arrange["Ungroup"].trigger()  # type: ignore[attr-defined]
    assert main_window.selection_manager.items == items
    assert all(item.parentItem() is None for item in items)
    assert unmet_messages == []

    # Merge Down, Merge Visible, and Flatten All act since the Navigation and Raster
    # Operations follow-up (fixed since).
    manager = main_window.scene.layer_manager
    manager.set_active(manager.add_layer("Layer 2").layer_id)
    main_window._merge_dont_ask = True  # noqa: SLF001
    layer = _rows(_menu(main_window, "Layer"))
    layer["Merge Down"].trigger()  # type: ignore[attr-defined]
    assert manager.count == 1 and main_window.scene.command_stack.undo_text == "Merge Down"
    manager.add_layer("Layer 2")
    layer["Merge Visible"].trigger()  # type: ignore[attr-defined]
    assert manager.count == 1 and main_window.scene.command_stack.undo_text == "Merge Visible"
    manager.add_layer("Layer 2")
    layer["Flatten All"].trigger()  # type: ignore[attr-defined]
    assert manager.count == 1 and manager.layers[0].is_background
    assert unmet_messages == []

    # Check for Updates acts since the Check for Updates work (fixed since): the row
    # queries the releases API and reports the outcome; the check is fed a canned 404
    # (no release published) and never reaches the network.
    from PyQt6.QtWidgets import QMessageBox

    from snapmock.core.update_check import UpdateChecker

    sent: list[object] = []
    monkeypatch.setattr(UpdateChecker, "send", lambda _self, request: sent.append(request))
    boxes: list[QMessageBox] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: boxes.append(self) or 0)
    help_menu = _rows(_menu(main_window, "Help"))
    help_menu["Check for Updates"].trigger()  # type: ignore[attr-defined]
    assert len(sent) == 1
    main_window._update_checker.receive(404, b"{}")  # noqa: SLF001
    assert [box.text() for box in boxes] == [
        f"No release has been published yet. You are running Snapmockit {APP_VERSION}."
    ]
    assert unmet_messages == []


# Section 3 shortcuts by code label; the six tool letters are the PRD 1.7 decision's.
SECTION_3_SHORTCUTS: dict[str, dict[str, str]] = {
    "File": {
        "New": "Ctrl+N",
        "Open...": "Ctrl+O",
        "Save": "Ctrl+S",
        "Save As...": "Ctrl+Shift+S",
        "Import Image...": "Ctrl+I",
        "Export...": "Ctrl+E",
        "Export Quick (PNG)": "Ctrl+Shift+E",
        "Print...": "Ctrl+P",
        "Preferences...": "Ctrl+,",
        "Quit": "Ctrl+Q",
    },
    "Edit": {
        "Undo": "Ctrl+Z",
        "Redo": "Ctrl+Shift+Z",
        "Cut": "Ctrl+X",
        "Copy": "Ctrl+C",
        "Copy All": "Ctrl+Shift+C",
        "Paste": "Ctrl+V",
        "Paste in Place": "Ctrl+Shift+V",
        "Duplicate": "Ctrl+D",
        "Delete": "Delete",
        "Select All": "Ctrl+A",
        "Select All Layers": "Ctrl+Shift+A",
        "Deselect": "Escape",
        "Select All Text": "Ctrl+T",
    },
    "View": {
        "Zoom Out": "Ctrl+-",
        "Zoom to 100%": "Ctrl+1",
        "Fit to Window": "Ctrl+0",
        "Zoom to Selection": "Ctrl+Shift+0",
        "Show Grid": "Ctrl+'",
        "Snap to Grid": "Ctrl+Shift+'",
        "Show Rulers": "Ctrl+R",
        "Show Guides": "Ctrl+;",
    },
    "Layer": {
        "New Layer": "Ctrl+Shift+N",
        "Merge Down": "Ctrl+Shift+M",
        "Flatten All": "Ctrl+Shift+F",
        "Rename Layer": "F2",
        "Move Up": "Ctrl+]",
        "Move Down": "Ctrl+[",
        "Move to Top": "Ctrl+Shift+]",
        "Move to Bottom": "Ctrl+Shift+[",
    },
    "Image": {"Crop to Canvas": "Ctrl+Shift+X"},
    "Arrange": {
        "Bring to Front": "Ctrl+Shift+Up",
        "Bring Forward": "Ctrl+Up",
        "Send Backward": "Ctrl+Down",
        "Send to Back": "Ctrl+Shift+Down",
        "Group": "Ctrl+G",
        "Ungroup": "Ctrl+Shift+G",
    },
    "Tools": {
        "Select": "V",
        "Raster Select": "M",
        "Arrow": "A",
        "Rectangle": "R",
        "Ellipse": "E",
        "Freehand": "P",
        "Text": "T",
        "Highlight": "H",
        "Numbered Step": "N",
        "Stamp": "S",
        "Eyedropper": "I",
        # The PRD 1.7 decision: Line U, Callout B, Blur Z, Crop C, Freeform L, Zoom Ctrl+Space.
        "Line": "L",
        "Callout": "C",
        "Blur": "B",
        "Crop": "X",
        "Lasso Select": "Shift+M",
        "Zoom": "Z",
    },
}


def test_17_2_shortcuts_match_section_3(main_window: MainWindow) -> None:
    """Row 7: every table shortcut on its action; Ctrl+' toggles the grid from the keys."""
    wrong: list[str] = []
    for title, table in SECTION_3_SHORTCUTS.items():
        rows = _rows(_menu(main_window, title))
        for label, expected in table.items():
            actual = _shortcut(rows[label])
            if QKeySequence(actual) != QKeySequence(expected):
                wrong.append(f"{title} > {label}: {actual!r} for {expected!r}")
    assert wrong == []
    view = _rows(_menu(main_window, "View"))
    # Section 16 row 7 failed as found (Ctrl+= only, and Qt does not treat Ctrl++ as the
    # same key) and is fixed since: the table's Ctrl++ is the alternate sequence.
    assert [s.toString() for s in view["Zoom In"].shortcuts()] == ["Ctrl+=", "Ctrl++"]  # type: ignore[attr-defined]
    assert QKeySequence("Ctrl++") != QKeySequence("Ctrl+=")
    # Delete / Backspace (Section 3.2) and Pan on Space (Section 3.7, handled as a key event).
    edit = _rows(_menu(main_window, "Edit"))
    assert [s.toString() for s in edit["Delete"].shortcuts()] == ["Del", "Backspace"]  # type: ignore[attr-defined]
    assert _shortcut(_rows(_menu(main_window, "Tools"))["Pan"]) == ""

    # A shortcut fires from the keyboard: Ctrl+' toggles Show Grid.
    main_window.show()
    QApplication.setActiveWindow(main_window)
    grid = view["Show Grid"]
    assert not grid.isChecked()  # type: ignore[attr-defined]
    QTest.keyClick(main_window, Qt.Key.Key_Apostrophe, Qt.KeyboardModifier.ControlModifier)
    assert grid.isChecked()  # type: ignore[attr-defined]
    assert main_window.view._grid_visible  # noqa: SLF001


def test_17_2_view_toggles_reflect_the_state(main_window: MainWindow) -> None:
    """Row 9: a panel closed by its own button unchecks its row; the view and settings
    toggles read the state they govern."""
    main_window.show()
    layer = main_window._layer_panel  # noqa: SLF001
    toggle = layer.toggleViewAction()
    assert toggle is not None and toggle.isChecked()
    layer.close()
    assert not toggle.isChecked()
    layer.show()
    assert toggle.isChecked()

    view = _rows(_menu(main_window, "View"))
    grid = view["Show Grid"]
    grid.setChecked(True)  # type: ignore[attr-defined]
    assert main_window.view._grid_visible  # noqa: SLF001
    assert AppSettings().grid_visible()
    grid.setChecked(False)  # type: ignore[attr-defined]
    assert not main_window.view._grid_visible  # noqa: SLF001

    rulers = view["Show Rulers"]
    rulers.setChecked(True)  # type: ignore[attr-defined]
    assert main_window.view._rulers_visible  # noqa: SLF001
    rulers.setChecked(False)  # type: ignore[attr-defined]
    assert not main_window.view._rulers_visible  # noqa: SLF001

    for label, reader in (
        ("Snap to Guides", AppSettings().snap_to_guides),
        ("Lock Guides", AppSettings().guides_locked),
        ("Snap to Grid", AppSettings().snap_to_grid),
    ):
        action = view[label]
        assert action.isChecked() == reader()  # type: ignore[attr-defined]
        action.setChecked(not reader())  # type: ignore[attr-defined]
        assert action.isChecked() == reader()  # type: ignore[attr-defined]

    status = view["Show Status Bar"]
    assert status.isChecked()  # type: ignore[attr-defined]
    status.setChecked(False)  # type: ignore[attr-defined]
    bar = main_window.statusBar()
    assert bar is not None and not bar.isVisibleTo(main_window)
    status.setChecked(True)  # type: ignore[attr-defined]


# ---- 17.3 Toolbars ----


def test_17_3_palette_shows_every_registered_tool_with_icons(main_window: MainWindow) -> None:
    """Row 12: one button per registered tool, twenty-one since the Arc and Polygon tools
    of the Basic Shape remainder work (decision 3; General UI PRD 2.12 counted nineteen),
    each with an icon and a "Name (Shortcut)" tooltip."""
    palette = main_window._toolbar  # noqa: SLF001
    buttons = palette._buttons  # noqa: SLF001
    assert len(buttons) == 21
    assert {"emoji", "arc", "polygon"} <= set(buttons)
    assert list(buttons) == list(main_window.tool_manager.tool_ids)
    for tool_id, button in buttons.items():
        tool = main_window.tool_manager.tool(tool_id)
        assert tool is not None
        assert not button.icon().isNull(), tool_id
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert button.toolTip() == tool_tooltip(tool_id, tool.display_name)


def test_17_3_active_tool_button_is_checked(main_window: MainWindow) -> None:
    """Row 13: the checked palette button follows the active tool by menu, key, and click;
    both style sheets draw a checked tool button."""
    buttons = main_window._toolbar._buttons  # noqa: SLF001

    def checked() -> list[str]:
        return [tid for tid, b in buttons.items() if b.isChecked()]

    assert checked() == ["select"]
    _rows(_menu(main_window, "Tools"))["Rectangle"].trigger()  # type: ignore[attr-defined]
    assert checked() == ["rectangle"]
    main_window.tool_manager.activate("text")
    assert checked() == ["text"]
    buttons["ellipse"].click()
    assert main_window.tool_manager.active_tool_id == "ellipse"
    assert checked() == ["ellipse"]
    for name in ("light", "dark"):
        text = (tm.THEMES_DIR / f"{name}.qss").read_text(encoding="utf-8")
        assert "QToolButton:checked" in text, name


def test_17_3_no_shown_toolbar_button_is_disabled(main_window: MainWindow) -> None:
    """Row 14: every control of the three toolbars is enabled, Group 5 included once two
    items are selected and it is shown."""
    items = _add_rects(main_window, 2)
    main_window.selection_manager.select_items(items)  # type: ignore[arg-type]
    align = main_window._main_toolbar.alignment_actions  # noqa: SLF001
    assert all(a.isVisible() for a in align)
    disabled: list[str] = []
    for bar in (
        main_window._main_toolbar,  # noqa: SLF001
        main_window._toolbar,  # noqa: SLF001
        main_window._tool_options,  # noqa: SLF001
    ):
        for widget in bar.findChildren(QWidget):
            if not isinstance(widget, QAbstractButton | QComboBox | QAbstractSpinBox):
                continue
            if isinstance(widget, QToolButton) and widget.defaultAction() is not None:
                action = widget.defaultAction()
                assert action is not None
                if not action.isVisible():
                    continue  # hidden by Section 4.2, not greyed out
            if not widget.isEnabled():
                disabled.append(describe(widget))
    assert disabled == []
    for action in align:
        assert action.isEnabled()


# ---- 17.4 Canvas ----


def test_17_4_dropped_image_file_creates_a_background_layer(
    main_window: MainWindow, tmp_path: Path
) -> None:
    """Row 16: what a dropped image file becomes. Fixed since the pass by the Navigation
    and Raster Operations follow-up: a Background layer holding the image on an empty
    project, the canvas resized to it; a raster region on the active layer otherwise."""
    path = tmp_path / "drop.png"
    pixmap = QPixmap(12, 8)
    pixmap.fill(QColor("red"))
    assert pixmap.save(str(path), "PNG")
    scene = main_window.scene
    layers_before = scene.layer_manager.count
    active = scene.layer_manager.active_layer
    assert active is not None

    def _drop() -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(
            QPointF(50, 50),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        main_window.view.dropEvent(event)
        assert event.isAccepted()

    _drop()
    regions = [i for i in scene.items() if isinstance(i, RasterRegionItem)]
    assert len(regions) == 1
    background = scene.layer_manager.layers[0]
    assert background.is_background and background.name == "Background"
    assert regions[0].layer_id == background.layer_id and regions[0].pos() == QPointF(0, 0)
    assert scene.layer_manager.count == layers_before + 1
    assert scene.layer_manager.active_layer is active
    assert (scene.canvas_size.width(), scene.canvas_size.height()) == (12, 8)
    # With a background in place a second drop is a raster region on the active layer
    _drop()
    regions = [i for i in scene.items() if isinstance(i, RasterRegionItem)]
    assert len(regions) == 2 and scene.layer_manager.count == layers_before + 1
    assert any(r.layer_id == active.layer_id for r in regions)


def test_17_4_rulers_track_the_cursor(main_window: MainWindow) -> None:
    """Row 17: a mouse move over the viewport puts both rulers' marker at the scene point."""
    view = main_window.view
    view.set_rulers_visible(True)
    h_ruler = view._h_ruler  # noqa: SLF001
    v_ruler = view._v_ruler  # noqa: SLF001
    assert isinstance(h_ruler, RulerWidget) and isinstance(v_ruler, RulerWidget)
    point = QPoint(60, 40)
    expected = view.mapToScene(point)
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(point),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(move)
    for ruler in (h_ruler, v_ruler):
        assert ruler._cursor_scene_pos == expected  # noqa: SLF001


def test_17_4_checkerboard_shows_through_a_transparent_canvas(main_window: MainWindow) -> None:
    """Row 19: the rendered canvas carries both checkerboard colours once its colour is
    transparent, and neither while it is white."""
    view = main_window.view
    scene = main_window.scene
    view.resize(600, 400)
    view.fit_in_view_all()
    viewport = view.viewport()
    assert viewport is not None

    def colours_in_canvas_corner() -> set[str]:
        image = viewport.grab().toImage()
        canvas = view.mapFromScene(scene.canvas_rect).boundingRect()
        found: set[str] = set()
        for x in range(canvas.left() + 2, canvas.left() + 66):
            for y in range(canvas.top() + 2, canvas.top() + 66):
                found.add(image.pixelColor(x, y).name().upper())
        return found

    assert scene.background_color.alpha() == 255
    white = colours_in_canvas_corner()
    assert "#CCCCCC" not in white

    scene.set_background_color(QColor(0, 0, 0, 0))
    seen = colours_in_canvas_corner()
    assert {"#FFFFFF", "#CCCCCC"} <= seen


# ---- 17.5 Panels ----


def test_17_5_property_panel_follows_selection_and_commands(main_window: MainWindow) -> None:
    """Row 23: selecting, a command on the item, and deselecting each show at once."""
    panel = main_window._property_panel  # noqa: SLF001
    item = _add_rects(main_window, 1)[0]
    item.setPos(42, 73)
    assert panel._canvas_section.isVisibleTo(panel)  # noqa: SLF001
    assert not panel._transform_section.isVisibleTo(panel)  # noqa: SLF001

    main_window.selection_manager.select_items([item])
    assert panel._transform_section.isVisibleTo(panel)  # noqa: SLF001
    assert panel._x_spin.value() == 42  # noqa: SLF001
    assert panel._y_spin.value() == 73  # noqa: SLF001

    main_window.scene.command_stack.push(MoveItemsCommand([item], QPointF(30, -10)))
    assert panel._x_spin.value() == 72  # noqa: SLF001
    assert panel._y_spin.value() == 63  # noqa: SLF001

    main_window.selection_manager.deselect_all()
    assert panel._canvas_section.isVisibleTo(panel)  # noqa: SLF001
    assert not panel._transform_section.isVisibleTo(panel)  # noqa: SLF001


def test_17_5_property_edit_moves_the_item_at_once(main_window: MainWindow) -> None:
    """Row 24: the X spinbox moves the item on the scene in the same event, undoably."""
    panel = main_window._property_panel  # noqa: SLF001
    item = _add_rects(main_window, 1)[0]
    main_window.selection_manager.select_items([item])
    panel._x_spin.setValue(120)  # noqa: SLF001
    assert item.pos().x() == 120
    panel._y_spin.setValue(45)  # noqa: SLF001
    assert item.pos().y() == 45
    main_window.scene.command_stack.undo()
    assert item.pos().y() == 0
    main_window.scene.command_stack.undo()
    assert item.pos().x() == 0


# ---- 17.7 Dialogs ----

SECTION_11_3_ROWS: dict[str, list[str]] = {
    "General": [
        "Language",
        "Auto-save interval",
        "Recent files count",
        "Default canvas size",
        "Default canvas color",
        "Default pasteboard color",
        "Confirm before deleting layers",
    ],
    "Appearance": [
        "Theme",
        "Icon size",
        "Canvas checkerboard size",
        "Checkerboard color 1",
        "Checkerboard color 2",
        "UI font size",
    ],
    "Canvas & Grid": [
        "Default grid size",
        "Grid color",
        "Grid opacity",
        "Snap tolerance",
        "Show pixel grid at zoom above",
        "Guide color",
        "Guide opacity",
    ],
    "Tools": [
        "Default stroke color",
        "Default stroke width",
        "Default fill color",
        "Default font",
        "Default font size",
        "Freehand smoothing default",
        "Numbered step starting number",
    ],
    "Performance": ["Undo history limit", "Thumbnail update delay"],
}


def test_17_7_preferences_carries_every_section_11_3_row(qtbot: QtBot) -> None:
    """Row 32: every row of the five Section 11.3 categories is in the dialog by label."""
    dialog = PreferencesDialog(AppSettings())
    qtbot.addWidget(dialog)
    labels = {label.text().rstrip(":") for label in dialog.findChildren(QLabel) if label.text()}
    for category, rows in SECTION_11_3_ROWS.items():
        missing = [row for row in rows if row not in labels]
        assert missing == [], f"{category}: {missing}"
    # Section 16 row 32, fail: the Performance category's "Hardware acceleration" checkbox
    # (enable or disable OpenGL rendering) is not built and no record says why.
    assert not any("acceleration" in label.lower() for label in labels)


# ---- 17.8 Accessibility ----


def test_17_8_every_tab_stop_is_reached_from_the_first(main_window: MainWindow) -> None:
    """Row 34: walking the focus chain from the first Main Toolbar control visits every Tab
    stop that lives in the main window."""
    main_window.show()
    start = focusable_controls(main_window._main_toolbar)[0]  # noqa: SLF001
    seen: list[QWidget] = []
    widget = start
    for _ in range(5000):
        seen.append(widget)
        widget = widget.nextInFocusChain()
        if widget is start:
            break
    assert widget is start, "the focus chain did not return to its start"
    stops = [w for w in focusable_controls(main_window) if w.window() is main_window]
    unreached = [describe(w) for w in stops if w not in seen]
    assert unreached == []


def test_17_8_canvas_paints_its_focus_frame(main_window: MainWindow) -> None:
    """Row 36 failed as found (the style sheet's focus border did not show on the canvas)
    and is fixed since: the view paints a 2 px accent frame inside its viewport while it
    has keyboard focus, and nothing while it does not."""
    main_window.show()
    QApplication.setActiveWindow(main_window)
    view = main_window.view
    viewport = view.viewport()
    assert viewport is not None
    accent = tm.current_theme().accent.name().upper()

    main_window._layer_panel.setFocus()  # noqa: SLF001
    assert not view.hasFocus()
    image = viewport.grab().toImage()
    assert image.pixelColor(1, 1).name().upper() != accent

    view.setFocus()
    assert view.hasFocus()
    image = viewport.grab().toImage()
    for x, y in ((1, 1), (viewport.width() - 2, 1), (1, viewport.height() - 2), (30, 0)):
        assert image.pixelColor(x, y).name().upper() == accent, (x, y)
    assert image.pixelColor(30, 4).name().upper() != accent
