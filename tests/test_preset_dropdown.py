"""The preset dropdown of the Tool Options Bar and the last-used option values
(General UI PRD 5.2, 15.4; Phase 7 steps 3 and 5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QToolButton
from pytestqt.qtbot import QtBot

from snapmock.core.tool_themes import CUSTOM_LABEL, DEFAULT_THEME_NAME
from snapmock.main_window import MainWindow
from snapmock.ui.preferences_dialog import PreferencesDialog
from snapmock.ui.tool_options_bar import ToolOptionsBar


def _bar(window: MainWindow) -> ToolOptionsBar:
    return window._tool_options  # noqa: SLF001


def _button(window: MainWindow) -> QToolButton:
    button = _bar(window).preset_button
    assert button is not None
    return button


def _menu_texts(window: MainWindow) -> list[str]:
    bar = _bar(window)
    bar._populate_preset_menu()  # noqa: SLF001
    menu = bar._preset_menu  # noqa: SLF001
    assert menu is not None
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _trigger(window: MainWindow, text: str) -> None:
    bar = _bar(window)
    bar._populate_preset_menu()  # noqa: SLF001
    menu = bar._preset_menu  # noqa: SLF001
    assert menu is not None
    for action in menu.actions():
        if action.text() == text:
            action.trigger()
            return
    raise AssertionError(f"no row {text!r}")


def _width_spin(window: MainWindow) -> QDoubleSpinBox:
    spin = _bar(window).shared_widgets["stroke_width"]
    assert isinstance(spin, QDoubleSpinBox)
    return spin


def test_dropdown_is_the_leftmost_control_of_a_tool_with_defaults(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("arrow")
    bar = _bar(main_window)
    first = bar.controls[0]
    assert isinstance(first, QToolButton)
    assert first is bar.preset_button
    assert first.objectName() == "PresetDropdown"
    assert first.accessibleName() == "Arrow preset"
    assert first.text() == f"{DEFAULT_THEME_NAME} ▾"
    second = bar.controls[1]
    assert isinstance(second, QLabel) and second.text().startswith("Arrow")

    main_window.tool_manager.activate("select")
    assert bar.preset_button is None
    main_window.tool_manager.activate("crop")
    assert bar.preset_button is None


def test_dropdown_reads_custom_after_an_edit_on_any_surface(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("rectangle")
    _width_spin(main_window).setValue(9.0)
    assert _button(main_window).text() == f"{CUSTOM_LABEL} ▾"
    assert main_window._tool_themes.is_modified()  # noqa: SLF001

    panel = main_window._property_panel  # noqa: SLF001
    panel._stroke_w_spin.setValue(2.0)  # noqa: SLF001
    assert _button(main_window).text() == f"{DEFAULT_THEME_NAME} ▾"


def test_save_as_preset_and_the_menu_rows(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_window.tool_manager.activate("arrow")
    assert _menu_texts(main_window) == ["Save as Preset...", "Manage Presets...", "Reset to Theme"]
    _width_spin(main_window).setValue(5.0)
    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": "Thick")
    _trigger(main_window, "Save as Preset...")
    assert _button(main_window).text() == "Thick ▾"
    assert (tmp_path / "snapmock-data" / "presets" / "arrow" / "thick.json").is_file()
    assert _menu_texts(main_window) == [
        "Thick",
        "Save as Preset...",
        "Manage Presets...",
        "Reset to Theme",
    ]
    bar = _bar(main_window)
    menu = bar._preset_menu  # noqa: SLF001
    assert menu is not None
    assert menu.actions()[0].isChecked()

    _width_spin(main_window).setValue(6.0)
    assert _button(main_window).text() == f"{CUSTOM_LABEL} ▾"
    assert _menu_texts(main_window) == [
        "Thick",
        "Save as Preset...",
        "Update Preset",
        "Manage Presets...",
        "Reset to Theme",
    ]
    assert not menu.actions()[0].isChecked()
    _trigger(main_window, "Update Preset")
    assert _button(main_window).text() == "Thick ▾"
    themes = main_window._tool_themes  # noqa: SLF001
    assert themes.presets("arrow")[0].values["stroke_width"] == 6.0

    _width_spin(main_window).setValue(1.0)
    _trigger(main_window, "Thick")
    assert _width_spin(main_window).value() == 6.0
    assert _button(main_window).text() == "Thick ▾"


def test_save_as_preset_needs_a_name_and_confirms_a_replacement(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    unmet_messages: list[tuple[str, str]],
) -> None:
    main_window.tool_manager.activate("arrow")
    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": "")
    _trigger(main_window, "Save as Preset...")
    assert unmet_messages == [("Save as Preset", "Save as Preset needs a preset name.")]
    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": None)
    _trigger(main_window, "Save as Preset...")
    assert main_window._tool_themes.preset_names("arrow") == []  # noqa: SLF001

    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": "One")
    _trigger(main_window, "Save as Preset...")
    _width_spin(main_window).setValue(8.0)
    monkeypatch.setattr(ToolOptionsBar, "_confirm_replace", lambda self, name: False)
    _trigger(main_window, "Save as Preset...")
    themes = main_window._tool_themes  # noqa: SLF001
    assert themes.presets("arrow")[0].values["stroke_width"] == 2.0
    monkeypatch.setattr(ToolOptionsBar, "_confirm_replace", lambda self, name: True)
    _trigger(main_window, "Save as Preset...")
    assert themes.presets("arrow")[0].values["stroke_width"] == 8.0
    assert themes.preset_names("arrow") == ["One"]


def test_reset_to_theme(main_window: MainWindow, unmet_messages: list[tuple[str, str]]) -> None:
    main_window.tool_manager.activate("ellipse")
    _trigger(main_window, "Reset to Theme")
    assert unmet_messages == [
        ("Reset to Theme", "Reset to Theme needs a setting that differs from the active theme.")
    ]
    _width_spin(main_window).setValue(7.5)
    _trigger(main_window, "Reset to Theme")
    assert _width_spin(main_window).value() == 2.0
    assert _button(main_window).text() == f"{DEFAULT_THEME_NAME} ▾"


def test_option_values_and_presets_persist_across_sessions(
    main_window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_window.tool_manager.activate("arrow")
    _width_spin(main_window).setValue(4.5)
    main_window.tool_manager.activate("rectangle")
    _width_spin(main_window).setValue(3.0)
    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": "Three")
    _trigger(main_window, "Save as Preset...")
    main_window._save_window_state()  # noqa: SLF001
    assert (tmp_path / "snapmock-data" / "tool_state.json").is_file()

    second = MainWindow()
    qtbot.addWidget(second)
    arrow = second.tool_manager.tool("arrow")
    rect = second.tool_manager.tool("rectangle")
    assert arrow is not None and rect is not None
    assert arrow.creation_defaults["stroke_width"] == 4.5
    assert rect.creation_defaults["stroke_width"] == 3.0
    themes = second._tool_themes  # noqa: SLF001
    assert themes.applied_preset("rectangle") == "Three"
    assert themes.current_label("rectangle") == "Three"
    assert themes.current_label("arrow") == CUSTOM_LABEL
    second.tool_manager.activate("rectangle")
    assert _button(second).text() == "Three ▾"


def test_preferences_edit_the_default_theme_around_overrides(
    main_window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_window.tool_manager.activate("arrow")
    _width_spin(main_window).setValue(5.0)
    monkeypatch.setattr(ToolOptionsBar, "_ask_preset_name", lambda self, initial="": "Five")
    _trigger(main_window, "Save as Preset...")
    main_window._apply_preference_changes(  # noqa: SLF001
        {"default_stroke_width": (2.0, 11.0), "default_stroke_color": (None, QColor("#0000FF"))}
    )
    arrow = main_window.tool_manager.tool("arrow")
    ellipse = main_window.tool_manager.tool("ellipse")
    assert arrow is not None and ellipse is not None
    assert arrow.creation_defaults["stroke_width"] == 5.0
    assert ellipse.creation_defaults["stroke_width"] == 11.0
    assert ellipse.creation_defaults["stroke_color"] == QColor("#0000FF")
    themes = main_window._tool_themes  # noqa: SLF001
    assert themes.default_theme().tools["arrow"]["stroke_width"] == 11.0
    assert themes.current_label("arrow") == "Five"
    assert themes.current_label("ellipse") == DEFAULT_THEME_NAME

    dlg = PreferencesDialog(main_window._settings, active_theme="Blue")  # noqa: SLF001
    qtbot.addWidget(dlg)
    note = dlg.findChild(QLabel, "ToolsThemeNote")
    assert note is not None
    assert "Default tool theme" in note.text() and "Active theme: Blue." in note.text()


def test_window_writes_to_the_isolated_data_directory(
    main_window: MainWindow, tmp_path: Path
) -> None:
    assert main_window._tool_themes.root == tmp_path / "snapmock-data"  # noqa: SLF001
