"""The Welcome panel and first-run defaults of General UI PRD Section 16."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog
from pytestqt.qtbot import QtBot

from snapmock.config.settings import AppSettings
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.main_window import MainWindow
from snapmock.ui.welcome_panel import (
    CARD_NEW_CANVAS,
    CARD_OPEN_IMAGE,
    CARD_PASTE,
    CARDS,
    STEPS,
    TAGLINE,
    CanvasSizeDialog,
    WelcomePanel,
)


def _first_run() -> None:
    """Undo the conftest answer: this test is the very first launch."""
    settings = AppSettings()
    settings.set_first_run_done(False)
    settings.set_show_welcome_at_startup(False)


def _window(qtbot: QtBot) -> MainWindow:
    window = MainWindow()

    def _clean(w: MainWindow) -> None:
        for doc in w.documents.documents:
            doc.scene.command_stack.mark_clean()

    qtbot.addWidget(window, before_close_func=_clean)
    return window


def _panel(window: MainWindow) -> WelcomePanel:
    panel = window.welcome_panel
    assert panel is not None
    return panel


def _raster_items(window: MainWindow) -> list[RasterRegionItem]:
    return [i for i in window.scene.items() if isinstance(i, RasterRegionItem)]


class TestFirstRun:
    def test_first_launch_writes_the_section_16_2_defaults_once(self, qtbot: QtBot) -> None:
        _first_run()
        assert AppSettings().snap_to_grid() is False
        window = _window(qtbot)
        settings = AppSettings()
        assert settings.first_run_done() is True
        assert settings.snap_to_grid() is True
        assert settings.theme_mode() == "system"
        assert settings.show_welcome_at_startup() is True
        assert window.tool_manager.active_tool_id == "select"
        assert window._snap_grid_action.isChecked()  # noqa: SLF001
        # A later launch keeps the user's changes.
        settings.set_snap_to_grid(False)
        settings.set_theme_mode("dark")
        second = _window(qtbot)
        assert AppSettings().snap_to_grid() is False
        assert AppSettings().theme_mode() == "dark"
        assert second.welcome_is_showing()

    def test_first_launch_shows_the_panel_instead_of_the_canvas(self, qtbot: QtBot) -> None:
        _first_run()
        window = _window(qtbot)
        assert window.welcome_is_showing()
        assert window._tabs.stack.currentWidget() is window.welcome_panel  # noqa: SLF001
        assert not window._tabs.tab_bar.isVisibleTo(window)  # noqa: SLF001

    def test_after_the_first_run_the_panel_stays_away(self, qtbot: QtBot) -> None:
        window = _window(qtbot)
        assert not window.welcome_is_showing()
        assert window._tabs.stack.currentWidget() is window.view  # noqa: SLF001


class TestPanelContent:
    def test_logo_tagline_cards_steps_and_names(self, qtbot: QtBot) -> None:
        panel = WelcomePanel(AppSettings())
        qtbot.addWidget(panel)
        assert TAGLINE == "Snapmockit - Screenshot Annotation & UI Mockup Tool"
        assert [c[0] for c in CARDS] == [CARD_OPEN_IMAGE, CARD_PASTE, CARD_NEW_CANVAS]
        assert len(STEPS) == 4
        assert STEPS[0][0] == "Import or paste a screenshot"
        assert STEPS[3][0] == "Export or save your work"
        for title, description, _glyph in CARDS:
            card = panel.card(title)
            assert card.accessibleName() == title
            assert card.accessibleDescription() == description
        assert panel.dont_show_checkbox.accessibleName() == "Don't show this again"
        assert panel.close_button.accessibleName()
        assert panel.accessibleName() == "Welcome"

    def test_dont_show_again_writes_the_setting(self, qtbot: QtBot) -> None:
        settings = AppSettings()
        settings.set_show_welcome_at_startup(True)
        panel = WelcomePanel(settings)
        qtbot.addWidget(panel)
        assert not panel.dont_show_checkbox.isChecked()
        panel.dont_show_checkbox.setChecked(True)
        assert AppSettings().show_welcome_at_startup() is False
        panel.dont_show_checkbox.setChecked(False)
        assert AppSettings().show_welcome_at_startup() is True


class TestRoutes:
    def test_help_menu_opens_and_close_returns_to_the_canvas(self, qtbot: QtBot) -> None:
        window = _window(qtbot)
        window._help_welcome()  # noqa: SLF001
        assert window.welcome_is_showing()
        _panel(window).close_button.click()
        assert not window.welcome_is_showing()
        assert window._tabs.stack.currentWidget() is window.view  # noqa: SLF001
        window.show_welcome()
        qtbot.keyClick(_panel(window), Qt.Key.Key_Escape)
        assert not window.welcome_is_showing()

    def test_open_an_image_imports_through_the_file_route(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        image = tmp_path / "shot.png"
        QPixmap(40, 30).save(str(image))
        window = _window(qtbot)
        window.show_welcome()
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
        _panel(window).card(CARD_OPEN_IMAGE).click()
        assert window.welcome_is_showing()
        assert _raster_items(window) == []
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(image), ""))
        _panel(window).card(CARD_OPEN_IMAGE).click()
        assert not window.welcome_is_showing()
        assert len(_raster_items(window)) == 1
        assert window.documents.count == 1

    def test_paste_card_checks_the_clipboard_then_pastes(
        self, qtbot: QtBot, unmet_messages: list[tuple[str, str]]
    ) -> None:
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        clipboard.clear()
        window = _window(qtbot)
        window.show_welcome()
        _panel(window).card(CARD_PASTE).click()
        assert unmet_messages == [
            ("Paste from Clipboard", "Paste from Clipboard needs content on the clipboard.")
        ]
        assert window.welcome_is_showing()
        clipboard.setImage(QImage(20, 20, QImage.Format.Format_ARGB32))
        _panel(window).card(CARD_PASTE).click()
        assert not window.welcome_is_showing()
        assert len(_raster_items(window)) == 1
        # "Pastes clipboard content as background" (Section 16.1): the Background layer
        # holds it and the canvas takes its size (follow-up step 5)
        lm = window.scene.layer_manager
        assert lm.background_layer is lm.layers[0]
        assert _raster_items(window)[0].layer_id == lm.layers[0].layer_id
        assert window.scene.canvas_size.width() == 20 and lm.active_layer is lm.layers[1]
        clipboard.clear()

    def test_new_blank_canvas_asks_a_size_and_opens_an_unsaved_document(
        self, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        window = _window(qtbot)
        window.show_welcome()
        seen: dict[str, tuple[int, int]] = {}

        def _cancel(dialog: CanvasSizeDialog) -> int:
            seen["initial"] = dialog.size_value()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(CanvasSizeDialog, "exec", _cancel)
        _panel(window).card(CARD_NEW_CANVAS).click()
        assert seen["initial"] == AppSettings().default_canvas_size()
        assert window.welcome_is_showing()
        assert window.documents.count == 1

        def _accept(dialog: CanvasSizeDialog) -> int:
            dialog.width_spin.setValue(800)
            dialog.height_spin.setValue(600)
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(CanvasSizeDialog, "exec", _accept)
        _panel(window).card(CARD_NEW_CANVAS).click()
        assert not window.welcome_is_showing()
        doc = window.active_document
        assert window.documents.count == 1
        assert doc.file_path is None
        assert not doc.is_library_file
        assert doc.display_name == "Untitled"
        assert (doc.scene.canvas_size.width(), doc.scene.canvas_size.height()) == (800, 600)

    def test_size_dialog_lock_aspect_ratio(self, qtbot: QtBot) -> None:
        dialog = CanvasSizeDialog(1920, 1080)
        qtbot.addWidget(dialog)
        dialog.width_spin.setValue(960)
        assert dialog.height_spin.value() == 1080
        dialog.lock_checkbox.setChecked(True)
        dialog.width_spin.setValue(1920)
        assert dialog.height_spin.value() == 1080
        dialog.height_spin.setValue(540)
        assert dialog.width_spin.value() == 960
        assert dialog.size_value() == (960, 540)

    def test_opening_a_document_leaves_the_panel(self, qtbot: QtBot) -> None:
        window = _window(qtbot)
        window.show_welcome()
        window._file_new()  # noqa: SLF001
        assert not window.welcome_is_showing()
        assert window._tabs.stack.currentWidget() is window.view  # noqa: SLF001
