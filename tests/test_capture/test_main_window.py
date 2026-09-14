"""Tests for the capture wiring in MainWindow and app bootstrap (PRD 3.2 to 3.5, 7, 12.1)."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QToolButton
from pytestqt.qtbot import QtBot

from snapmock.app import _capture_as_first_action
from snapmock.capture.backend import FakeCaptureBackend, FakeHotkeyBackend
from snapmock.capture.cli import CaptureCommand
from snapmock.capture.manager import MSG_BUSY, CaptureManager
from snapmock.capture.models import (
    HOTKEY_ACTION_REGION,
    ORIGIN_MENU,
    CaptureMode,
)
from snapmock.commands.add_item import AddItemCommand
from snapmock.config.settings import AppSettings
from snapmock.io.project_serializer import read_capture_metadata, read_manifest
from snapmock.items.rectangle_item import RectangleItem
from snapmock.library.file_info import LibraryFileInfo
from snapmock.main_window import MainWindow


def _menu(window: MainWindow, title: str) -> QMenu:
    bar = window.menuBar()
    assert bar is not None
    for action in bar.actions():
        menu = action.menu()
        if isinstance(menu, QMenu) and action.text() == title:
            return menu
    raise AssertionError(f"menu {title} missing")


def _fake_backend(window: MainWindow) -> FakeCaptureBackend:
    backend = window.capture_manager.backend
    assert isinstance(backend, FakeCaptureBackend)
    return backend


# --- menu, toolbar, shortcuts ---


def test_capture_menu_order_and_items(main_window: MainWindow) -> None:
    bar = main_window.menuBar()
    assert bar is not None
    titles = [a.text() for a in bar.actions() if isinstance(a.menu(), QMenu)]
    assert titles.index("&Capture") == titles.index("Li&brary") + 1
    assert titles.index("&Help") == titles.index("&Capture") + 1
    menu = _menu(main_window, "&Capture")
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == [
        "Capture &Region",
        "Capture Active &Window",
        "Capture &Full Screen",
        "&Delay",
        "Include Mouse &Cursor",
        "Copy to Clip&board",
        "&Hide Snapmockit During Capture",
        "Capture &Preferences...",
    ]
    assert "scrolling" not in " ".join(texts).lower()
    region = menu.actions()[0]
    assert region.shortcut() == QKeySequence("Print")
    assert menu.actions()[2].shortcut() == QKeySequence("Ctrl+Print")


def test_menu_shortcuts_follow_hotkey_preferences(main_window: MainWindow) -> None:
    main_window.capture_manager.set_hotkey(HOTKEY_ACTION_REGION, "F9")
    region = _menu(main_window, "&Capture").actions()[0]
    assert region.shortcut() == QKeySequence("F9")
    button = main_window.findChild(QToolButton, "")
    assert main_window._capture_button is not None  # noqa: SLF001
    assert main_window._capture_button.toolTip() == "Capture (F9)"  # noqa: SLF001
    assert button is not None


def test_toolbar_group_zero_is_first(main_window: MainWindow) -> None:
    toolbar = main_window._main_toolbar  # noqa: SLF001
    first = toolbar.widgetForAction(toolbar.actions()[0])
    assert isinstance(first, QToolButton) and first.text() == "Capture"
    assert first.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
    assert toolbar.actions()[1].isSeparator()
    assert first.toolTip() == "Capture (Print)"
    menu = first.menu()
    assert menu is not None
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels[:3] == [
        "Capture Region\tPrint",
        "Capture Active Window\tAlt+Print",
        "Capture Full Screen\tCtrl+Print",
    ]
    assert labels[3] == "&Delay"


def test_delay_and_toggles_sync_across_menus(main_window: MainWindow) -> None:
    menu = _menu(main_window, "&Capture")
    delay_menu = next(a.menu() for a in menu.actions() if a.text() == "&Delay")
    assert delay_menu is not None
    five = next(a for a in delay_menu.actions() if a.data() == 5)
    five.trigger()
    assert AppSettings().capture_delay_seconds() == 5
    toolbar_button = main_window._capture_button  # noqa: SLF001
    assert toolbar_button is not None
    tb_menu = toolbar_button.menu()
    assert tb_menu is not None
    tb_delay = next(a.menu() for a in tb_menu.actions() if a.text() == "&Delay")
    assert tb_delay is not None
    assert [a.isChecked() for a in tb_delay.actions()] == [False, False, True, False]
    cursor = next(a for a in menu.actions() if a.text() == "Include Mouse &Cursor")
    cursor.setChecked(True)
    assert AppSettings().capture_include_cursor() is True
    hide = next(a for a in menu.actions() if a.text() == "&Hide Snapmockit During Capture")
    assert hide.isChecked() is True
    hide.setChecked(False)
    assert AppSettings().capture_hide_window() is False


# --- post-capture flow ---


def test_menu_capture_creates_library_file_with_metadata(
    qtbot: QtBot, main_window: MainWindow
) -> None:
    AppSettings().set_capture_hide_window(False)
    AppSettings().set_capture_default_mode("full_screen")
    manager = main_window.capture_manager
    with qtbot.waitSignal(main_window.library.file_created, timeout=3000) as blocker:
        main_window._capture_button.click()  # type: ignore[union-attr]  # noqa: SLF001
    path = blocker.args[0]
    assert isinstance(path, Path) and path.name.startswith("Capture_")
    manifest = read_manifest(path)
    capture = manifest["capture_metadata"]
    assert capture["mode"] == "full_screen" and capture["requested_mode"] == "full_screen"
    assert capture["backend"] == "fake" and capture["cursor_included"] is False
    assert capture["screen_rect"] == {"x": 0, "y": 0, "width": 200, "height": 100}
    assert set(capture) == {
        "mode",
        "requested_mode",
        "monitor_name",
        "device_pixel_ratio",
        "screen_rect",
        "cursor_included",
        "platform",
        "backend",
        "window_title",
    }
    expected = manager.settings.capture_last_mode()
    assert expected == "full_screen"
    # captured_at is the grab time, to the second.
    taken = manifest["library_metadata"]["captured_at"]
    assert taken.endswith("Z")
    doc = main_window.active_document
    assert doc.file_path == path and doc.capture_metadata == capture
    assert doc.scene.command_stack.count == 0


def test_capture_metadata_survives_write_back(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    with qtbot.waitSignal(main_window.library.file_created, timeout=3000) as blocker:
        main_window._start_capture(CaptureMode.FULL_SCREEN, ORIGIN_MENU)  # noqa: SLF001
    path = blocker.args[0]
    doc = main_window.active_document
    layer = doc.scene.layer_manager.active_layer
    assert layer is not None
    doc.scene.command_stack.push(
        AddItemCommand(doc.scene, RectangleItem(rect=QRect(0, 0, 5, 5).toRectF()), layer.layer_id)
    )
    main_window.library.flush()
    assert read_capture_metadata(path) == doc.capture_metadata
    info = LibraryFileInfo.from_path(path)
    assert info.capture_metadata == doc.capture_metadata


def test_captured_at_equals_grab_time(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    manager = main_window.capture_manager
    with qtbot.waitSignal(manager.capture_completed, timeout=3000) as done:
        with qtbot.waitSignal(main_window.library.file_created, timeout=3000) as created:
            manager.start(manager.request_from_settings(CaptureMode.FULL_SCREEN))
    result = done.args[0]
    meta = read_manifest(created.args[0])["library_metadata"]
    assert meta["captured_at"] == result.taken_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_toast_mentions_clipboard(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    AppSettings().set_capture_copy_to_clipboard(True)
    with qtbot.waitSignal(main_window.library.file_created, timeout=3000):
        main_window._start_capture(CaptureMode.FULL_SCREEN, ORIGIN_MENU)  # noqa: SLF001
    label = main_window._toast._label.text()  # noqa: SLF001
    assert label.startswith("Captured to Library and clipboard: Capture_")


def test_failure_shows_toast_and_creates_no_file(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    _fake_backend(main_window).fail_with = "The portal is missing."
    with qtbot.waitSignal(main_window.capture_manager.capture_failed, timeout=3000):
        main_window._start_capture(CaptureMode.REGION, ORIGIN_MENU)  # noqa: SLF001
    assert main_window._toast._label.text() == "The portal is missing."  # noqa: SLF001
    assert main_window.library.list_files() == []


def test_busy_click_explains(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    manager = main_window.capture_manager
    assert manager.start(manager.request_from_settings(CaptureMode.REGION))
    main_window._capture_button.click()  # type: ignore[union-attr]  # noqa: SLF001
    assert main_window._toast._label.text() == MSG_BUSY  # noqa: SLF001
    manager.cancel()


def test_capture_leaves_dirty_document_alone(qtbot: QtBot, main_window: MainWindow) -> None:
    AppSettings().set_capture_hide_window(False)
    doc = main_window.active_document
    layer = doc.scene.layer_manager.active_layer
    assert layer is not None
    doc.scene.command_stack.push(
        AddItemCommand(doc.scene, RectangleItem(rect=QRect(0, 0, 5, 5).toRectF()), layer.layer_id)
    )
    assert doc.is_dirty
    with qtbot.waitSignal(main_window.library.file_created, timeout=3000):
        main_window._start_capture(CaptureMode.FULL_SCREEN, ORIGIN_MENU)  # noqa: SLF001
    assert main_window.active_document is not doc
    assert doc.is_dirty and doc.scene.command_stack.count == 1


def test_secondary_window_shares_manager(qtbot: QtBot, main_window: MainWindow) -> None:
    other = MainWindow(capture_manager=main_window.capture_manager, primary_capture=False)
    qtbot.addWidget(other)
    assert other.capture_manager is main_window.capture_manager
    assert other.tray_icon is None


# --- tray and keep running ---


@pytest.fixture()
def tray_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))


def test_tray_created_with_menu(qtbot: QtBot, tray_available: None) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    tray = window.tray_icon
    assert tray is not None and tray.toolTip() == "Snapmockit"
    menu = tray.contextMenu()
    assert menu is not None
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == [
        "Capture &Region",
        "Capture Active &Window",
        "Capture &Full Screen",
        "&Delay",
        "Include Mouse &Cursor",
        "Copy to Clip&board",
        "&Show Snapmockit",
        "&Preferences...",
        "&Quit Snapmockit",
    ]
    window.capture_manager.countdown_tick.emit(3)
    assert tray.toolTip() == "Snapmockit: capturing in 3 s"
    window.capture_manager.countdown_tick.emit(0)
    assert tray.toolTip() == "Snapmockit"


def test_tray_not_created_when_disabled(qtbot: QtBot, tray_available: None) -> None:
    AppSettings().set_capture_tray_enabled(False)
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.tray_icon is None


def test_keep_running_in_tray_hides_on_close(qtbot: QtBot, tray_available: None) -> None:
    AppSettings().set_capture_keep_running_in_tray(True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    app = QApplication.instance()
    assert isinstance(app, QApplication) and app.quitOnLastWindowClosed() is False
    window.close()
    assert not window.isVisible() and window.hidden_in_tray
    # Hotkeys still work: a capture while hidden reports through the tray, not a toast.
    AppSettings().set_capture_hide_window(False)
    with qtbot.waitSignal(window.library.file_created, timeout=3000):
        window._start_capture(CaptureMode.FULL_SCREEN, ORIGIN_MENU)  # noqa: SLF001
    assert window._toast._label.text() == ""  # noqa: SLF001
    window.show_from_tray()
    assert window.isVisible() and not window.hidden_in_tray
    window.quit_application()
    assert not window.isVisible()
    assert app.quitOnLastWindowClosed() is True


def test_close_without_keep_running_quits(qtbot: QtBot, tray_available: None) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.close()
    assert not window.isVisible() and not window.hidden_in_tray
    assert window.tray_icon is None


# --- hotkeys and command line ---


def test_hotkey_failure_toast_names_key(main_window: MainWindow) -> None:
    hk = main_window.capture_manager.hotkey_backend
    assert isinstance(hk, FakeHotkeyBackend)
    hk.refused.add("Print")
    main_window.capture_manager.register_hotkeys()
    main_window.report_hotkey_failures()
    assert main_window._toast._label.text() == (  # noqa: SLF001
        "Print is in use by another application. Change it in Preferences > Capture."
    )


def test_command_line_capture_as_first_action(qtbot: QtBot) -> None:
    AppSettings().set_capture_hide_window(True)
    window = MainWindow()
    qtbot.addWidget(window)
    manager: CaptureManager = window.capture_manager
    assert not window.isVisible()
    with qtbot.waitSignal(manager.capture_completed, timeout=3000):
        _capture_as_first_action(window, CaptureCommand(mode="full"), show_after=True)
    assert window.isVisible()
    assert window.library.list_files()
