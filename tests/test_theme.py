"""Tests for the theme manager (General UI PRD Section 13) and View > Dark Mode."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from snapmock.config.settings import AppSettings
from snapmock.core import theme_manager as tm
from snapmock.core.theme_manager import (
    COLOR_NAMES,
    ThemeMode,
    load_theme,
    parse_theme_file,
    reset_theme_manager,
    theme_manager,
)
from snapmock.main_window import MainWindow


@pytest.fixture(autouse=True)
def fresh_theme_manager() -> None:
    """Each test starts with no process-wide ThemeManager and ends the same way."""
    reset_theme_manager()
    yield
    reset_theme_manager()


class TestThemeFiles:
    def test_light_and_dark_define_every_colour(self) -> None:
        light = load_theme("light")
        dark = load_theme("dark")
        for name in COLOR_NAMES:
            assert getattr(light.colors, name).isValid(), name
            assert getattr(dark.colors, name).isValid(), name

    def test_tables_of_section_13(self) -> None:
        light = load_theme("light").colors
        dark = load_theme("dark").colors
        assert light.window_bg.name().upper() == "#F5F5F5"
        assert light.accent.name().upper() == "#2B579A"
        assert light.pasteboard.name().upper() == "#E0E0E0"
        assert dark.window_bg.name().upper() == "#2D2D2D"
        assert dark.accent.name().upper() == "#5B9BD5"
        assert dark.pasteboard.name().upper() == "#1E1E1E"
        assert light.grid_lines.alpha() == 0x33
        assert dark.grid_lines.alpha() == 0x26

    def test_constants_are_substituted_into_the_rules(self) -> None:
        light = load_theme("light")
        assert "@" not in light.style_sheet
        assert "#F5F5F5" in light.style_sheet

    def test_missing_constant_is_an_error(self) -> None:
        text = "@window-bg: #FFFFFF;\nQWidget { color: @text-primary; }"
        with pytest.raises(ValueError, match="lacks constants"):
            parse_theme_file(text, "broken")

    def test_undefined_reference_is_an_error(self) -> None:
        light_text = (tm.THEMES_DIR / "light.qss").read_text(encoding="utf-8")
        with pytest.raises(ValueError, match="undefined constant"):
            parse_theme_file(light_text + "\nQWidget { color: @nope; }", "broken")


class TestThemeManager:
    def test_default_is_light(self, qtbot: QtBot) -> None:
        manager = theme_manager()
        assert manager.mode is ThemeMode.LIGHT
        assert manager.resolved == "light"

    def test_set_mode_dark_applies_live(self, qtbot: QtBot, qapp: object) -> None:
        manager = theme_manager()
        manager.apply()
        with qtbot.waitSignal(manager.theme_changed) as blocker:
            manager.set_mode(ThemeMode.DARK)
        assert blocker.args == ["dark"]
        assert manager.resolved == "dark"
        assert manager.colors.window_bg.name().upper() == "#2D2D2D"
        assert "#2D2D2D" in qapp.styleSheet()  # type: ignore[attr-defined]
        assert qapp.palette().window().color().name().upper() == "#2D2D2D"  # type: ignore[attr-defined]

    def test_same_mode_does_not_reapply(self, qtbot: QtBot) -> None:
        manager = theme_manager()
        manager.apply()
        with qtbot.assertNotEmitted(manager.theme_changed):
            manager.set_mode(ThemeMode.LIGHT)

    def test_system_follows_the_style_hint(
        self, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = theme_manager()
        monkeypatch.setattr(tm, "system_prefers_dark", lambda: True)
        manager.set_mode(ThemeMode.SYSTEM)
        assert manager.resolved == "dark"
        monkeypatch.setattr(tm, "system_prefers_dark", lambda: False)
        manager.set_mode(ThemeMode.SYSTEM)
        assert manager.resolved == "light"

    def test_ui_font_size_changes_the_application_font(self, qtbot: QtBot, qapp: object) -> None:
        manager = theme_manager()
        manager.apply()
        base = qapp.font().pointSizeF()  # type: ignore[attr-defined]
        manager.set_ui_font_size("large")
        assert qapp.font().pointSizeF() == pytest.approx(base + 2)  # type: ignore[attr-defined]
        manager.set_ui_font_size("medium")
        assert qapp.font().pointSizeF() == pytest.approx(base)  # type: ignore[attr-defined]

    def test_icon_size_signal(self, qtbot: QtBot) -> None:
        manager = theme_manager()
        with qtbot.waitSignal(manager.icon_size_changed) as blocker:
            manager.set_icon_size(32)
        assert blocker.args == [32]
        assert manager.icon_size == 32
        manager.set_icon_size(99)
        assert manager.icon_size == 24

    def test_from_value_falls_back_to_light(self) -> None:
        assert ThemeMode.from_value("dark") is ThemeMode.DARK
        assert ThemeMode.from_value("bogus") is ThemeMode.LIGHT


class TestDarkModeMenu:
    def _dark_mode_action(self, window: MainWindow):  # type: ignore[no-untyped-def]
        return window._dark_mode_action

    def test_action_reflects_saved_theme(self, qtbot: QtBot) -> None:
        AppSettings().set_theme_mode("dark")
        window = MainWindow()
        qtbot.addWidget(window)
        assert self._dark_mode_action(window).isChecked() is True
        assert theme_manager().resolved == "dark"

    def test_toggle_persists_and_switches(self, main_window: MainWindow) -> None:
        action = self._dark_mode_action(main_window)
        assert action.isChecked() is False
        action.setChecked(True)
        assert theme_manager().resolved == "dark"
        assert AppSettings().theme_mode() == "dark"
        action.setChecked(False)
        assert theme_manager().resolved == "light"
        assert AppSettings().theme_mode() == "light"

    def test_preferences_mode_updates_the_action(self, main_window: MainWindow) -> None:
        main_window.set_theme_mode(ThemeMode.DARK)
        assert self._dark_mode_action(main_window).isChecked() is True
        assert AppSettings().theme_mode() == "dark"


class TestCanvasReadsTheme:
    def test_view_pasteboard_follows_the_theme(self, qtbot: QtBot, view) -> None:  # type: ignore[no-untyped-def]
        manager = theme_manager()
        manager.apply()
        assert view.pasteboard_color.name().upper() == "#E0E0E0"
        manager.set_mode(ThemeMode.DARK)
        assert view.pasteboard_color.name().upper() == "#1E1E1E"

    def test_pasteboard_override_wins_over_the_theme(self, qtbot: QtBot, view) -> None:  # type: ignore[no-untyped-def]
        from PyQt6.QtGui import QColor

        view.set_pasteboard_color(QColor("#808080"))
        assert view.pasteboard_color.name().upper() == "#808080"
        view.set_pasteboard_color(None)
        assert view.pasteboard_color.name().upper() == "#E0E0E0"

    def test_grid_pens_use_theme_alpha_unless_overridden(self, qtbot: QtBot, view) -> None:  # type: ignore[no-untyped-def]
        from PyQt6.QtGui import QColor

        minor, major = view._grid_pens()
        assert minor.color().alpha() == 0x33
        assert major.color().alpha() == 0x55
        view.set_grid_style(QColor("#FF0000"), 50)
        minor, major = view._grid_pens()
        assert minor.color().red() == 255
        assert minor.color().alpha() == round(50 * 2.55)

    def test_checkerboard_tile_uses_theme_colours_and_size(self, qtbot: QtBot, view) -> None:  # type: ignore[no-untyped-def]
        tile = view._get_checkerboard_tile()
        assert tile.width() == 16
        assert tile.toImage().pixelColor(0, 0).name().upper() == "#CCCCCC"
        assert tile.toImage().pixelColor(12, 4).name().upper() == "#FFFFFF"
        view.set_checkerboard(4, None)
        assert view._get_checkerboard_tile().width() == 8

    def test_handles_recolour_on_theme_change(self, main_window: MainWindow) -> None:
        from snapmock.tools.select_tool import SelectTool

        tool = main_window._tool_manager.tool("select")
        assert isinstance(tool, SelectTool)
        assert tool._handles is not None
        assert tool._handles._border.pen().color().name().upper() == "#2B579A"
        theme_manager().set_mode(ThemeMode.DARK)
        assert tool._handles._border.pen().color().name().upper() == "#5B9BD5"

    def test_capture_accent_is_the_theme_accent(self, qtbot: QtBot) -> None:
        from snapmock.capture.overlay import accent_color

        theme_manager().apply()
        assert accent_color().name().upper() == "#2B579A"
        theme_manager().set_mode(ThemeMode.DARK)
        assert accent_color().name().upper() == "#5B9BD5"


class TestIcons:
    def test_every_named_icon_file_exists(self) -> None:
        from snapmock.ui.icons import ACTION_ICONS, ADD_ICON, CAPTURE_ICON, REMOVE_ICON, TOOL_ICONS

        names = set(TOOL_ICONS.values()) | set(ACTION_ICONS.values())
        names |= {ADD_ICON, REMOVE_ICON, CAPTURE_ICON}
        missing = sorted(n for n in names if not (tm.ICONS_DIR / f"{n}.svg").exists())
        assert missing == []
        assert (tm.ICONS_DIR / "LICENSE").exists()

    def test_icon_is_rendered_and_recoloured(self, qtbot: QtBot) -> None:
        manager = theme_manager()
        icon = manager.icon("pointer")
        assert not icon.isNull()
        assert not icon.availableSizes()[0].isEmpty()
        assert manager.icon("no-such-glyph").isNull()
        light_key = ("pointer", "light")
        assert light_key in manager._icon_cache
        manager.set_mode(ThemeMode.DARK)
        assert light_key not in manager._icon_cache
        assert not manager.icon("pointer").isNull()

    def test_tool_palette_buttons_show_icons(self, main_window: MainWindow) -> None:
        from PyQt6.QtCore import Qt

        toolbar = main_window._toolbar
        for tool_id, btn in toolbar._buttons.items():
            assert not btn.icon().isNull(), tool_id
            assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert toolbar._buttons["select"].toolTip() == "Select (V)"
        assert toolbar.iconSize().width() == 24

    def test_icon_size_preference_resizes_the_palette(self, main_window: MainWindow) -> None:
        theme_manager().set_icon_size(32)
        assert main_window._toolbar.iconSize().width() == 32

    def test_menu_rows_have_icons(self, main_window: MainWindow) -> None:
        from snapmock.ui.icons import plain_label

        menu_bar = main_window.menuBar()
        assert menu_bar is not None
        file_menu = menu_bar.actions()[0].menu()
        assert file_menu is not None
        labels = {plain_label(a.text()): a for a in file_menu.actions() if not a.isSeparator()}
        assert not labels["Save"].icon().isNull()
        assert not labels["Export..."].icon().isNull()
        tools_action = main_window._tool_actions["rectangle"]
        assert not tools_action.icon().isNull()

    def test_plain_label_strips_accelerators(self) -> None:
        from snapmock.ui.icons import plain_label

        assert plain_label("&Save") == "Save"
        assert plain_label("Fish && Chips") == "Fish & Chips"


def test_reapplying_the_same_theme_leaves_the_style_sheet_alone(
    qapp: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting the application style sheet re-polishes every live widget, so a second
    window or a repeated apply of the same theme must not set it again (09-14-26)."""
    from PyQt6.QtWidgets import QApplication

    calls: list[str] = []
    original = QApplication.setStyleSheet

    def counting(self: QApplication, sheet: str) -> None:
        calls.append(sheet)
        original(self, sheet)

    monkeypatch.setattr(QApplication, "setStyleSheet", counting)
    manager = theme_manager()
    manager.set_mode(ThemeMode.DARK)
    manager.apply()
    manager.set_mode(ThemeMode.LIGHT)  # a change of theme sets the sheet
    after_change = len(calls)
    manager.apply()
    manager.apply()
    assert len(calls) == after_change  # the same sheet again, not set again
    manager.set_mode(ThemeMode.DARK)
    assert len(calls) == after_change + 1  # a different theme is set once
