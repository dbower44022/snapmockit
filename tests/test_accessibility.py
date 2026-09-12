"""Accessibility (General UI PRD Section 14): names, tab order, focus outline, contrast,
status bar announcements."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF, QSizeF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from snapmock.config.settings import AppSettings
from snapmock.core import theme_manager as tm
from snapmock.core.theme_manager import load_theme
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.ui.accessibility import (
    clean_label,
    describe,
    focusable_controls,
    unnamed_controls,
)


def _assert_all_named(root: QWidget) -> None:
    missing = unnamed_controls(root)
    assert missing == [], "\n".join(describe(w) for w in missing)


class TestAccessibleNames:
    def test_main_window_controls_are_named(self, main_window: MainWindow) -> None:
        _assert_all_named(main_window)
        assert main_window.menuBar().accessibleName() == "Menu bar"  # type: ignore[union-attr]
        assert main_window._main_toolbar.accessibleName() == "Main Toolbar"  # noqa: SLF001
        assert main_window._toolbar.accessibleName() == "Tool Palette"  # noqa: SLF001
        assert main_window._tool_options.accessibleName() == "Tool Options"  # noqa: SLF001
        assert main_window.view.accessibleName() == "Canvas"
        assert main_window._layer_panel.accessibleName() == "Layer Panel"  # noqa: SLF001
        assert main_window._property_panel.accessibleName() == "Property Panel"  # noqa: SLF001
        assert main_window._library_panel.accessibleName() == "Library Panel"  # noqa: SLF001
        assert main_window._status_bar.accessibleName() == "Status bar"  # noqa: SLF001

    def test_tool_palette_buttons_carry_a_name_and_a_description(
        self, main_window: MainWindow
    ) -> None:
        button = main_window._toolbar._buttons["rectangle"]  # noqa: SLF001
        assert button.accessibleName() == "Rectangle"
        assert "Rectangle" in button.accessibleDescription()

    def test_every_tools_options_bar_is_named(self, main_window: MainWindow) -> None:
        for tool_id in main_window.tool_manager.tool_ids:
            main_window.tool_manager.activate(tool_id)
            _assert_all_named(main_window._tool_options)  # noqa: SLF001
        main_window.tool_manager.activate("callout")
        names = {
            w.accessibleName()
            for w in main_window._tool_options.findChildren(QWidget)  # noqa: SLF001
            if w.accessibleName()
        }
        # The Callout's own two controls carry their own names, so the audit does not have
        # to take them from the label beside them (09-12-26, with the bar's overflow).
        assert {"Bubble shape", "Tail width", "Bold", "Straight"} <= names

    def test_document_tabs_and_close_buttons(self, main_window: MainWindow) -> None:
        main_window._file_new()  # noqa: SLF001
        main_window._file_new()  # noqa: SLF001
        bar = main_window._tabs.tab_bar  # noqa: SLF001
        assert bar.accessibleName() == "Document tabs"
        from PyQt6.QtWidgets import QTabBar

        close = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
        assert close is not None
        assert close.accessibleName() == "Close Untitled"

    def test_dialogs_are_named(self, main_window: MainWindow, qtbot: QtBot) -> None:
        from snapmock.ui.about_dialog import AboutDialog
        from snapmock.ui.find_replace_color_dialog import FindReplaceColorDialog
        from snapmock.ui.item_properties_dialog import ItemPropertiesDialog
        from snapmock.ui.layer_properties_dialog import LayerPropertiesDialog
        from snapmock.ui.preferences_dialog import PreferencesDialog
        from snapmock.ui.resize_canvas_dialog import ResizeCanvasDialog
        from snapmock.ui.resize_image_dialog import ResizeImageDialog
        from snapmock.ui.shortcuts_dialog import KeyboardShortcutsDialog
        from snapmock.ui.welcome_panel import CanvasSizeDialog, WelcomePanel

        layer = main_window.scene.layer_manager.active_layer
        assert layer is not None
        dialogs: list[QWidget] = [
            PreferencesDialog(AppSettings(), main_window, capture=main_window.capture_manager),
            KeyboardShortcutsDialog(main_window),
            AboutDialog(main_window),
            FindReplaceColorDialog(main_window.scene, main_window),
            ResizeCanvasDialog(QSizeF(100, 100), main_window),
            ResizeImageDialog(QSizeF(100, 100), main_window),
            LayerPropertiesDialog(layer, main_window),
            ItemPropertiesDialog(
                RectangleItem(rect=QRectF(0, 0, 10, 10)), main_window.scene, main_window
            ),
            main_window._export_dialog(),  # noqa: SLF001
            WelcomePanel(AppSettings()),
            CanvasSizeDialog(10, 10),
        ]
        for dialog in dialogs:
            qtbot.addWidget(dialog)
            _assert_all_named(dialog)

    def test_preferences_fields_take_their_row_labels(
        self, main_window: MainWindow, qtbot: QtBot
    ) -> None:
        from snapmock.ui.preferences_dialog import PreferencesDialog

        dlg = PreferencesDialog(AppSettings(), main_window, capture=main_window.capture_manager)
        qtbot.addWidget(dlg)
        assert dlg._recent_count_spin.accessibleName() == "Recent files count"  # noqa: SLF001
        assert dlg._theme_combo.accessibleName() == "Theme"  # noqa: SLF001
        names = {w.accessibleName() for w in dlg.findChildren(QWidget) if w.accessibleName()}
        assert "Region hotkey key" in names
        assert "Region hotkey Clear" in names

    def test_clean_label(self) -> None:
        assert clean_label("&Recent files count:") == "Recent files count"
        assert clean_label("Browse…") == "Browse"
        assert clean_label("Export...") == "Export"


class TestTabOrder:
    def test_zones_follow_the_prd_order(self, main_window: MainWindow) -> None:
        zones = [
            main_window._main_toolbar,  # noqa: SLF001
            main_window._tool_options,  # noqa: SLF001
            main_window._toolbar,  # noqa: SLF001
            main_window.view,
            main_window._layer_panel,  # noqa: SLF001
            main_window._property_panel,  # noqa: SLF001
        ]
        firsts = [focusable_controls(z)[0] for z in zones]
        start = firsts[0]
        seen: list[QWidget] = []
        w = start
        for _ in range(2000):
            seen.append(w)
            w = w.nextInFocusChain()
            if w is start:
                break
        positions = [seen.index(f) for f in firsts]
        assert positions == sorted(positions), [describe(f) for f in firsts]

    def test_order_survives_a_tool_change(self, main_window: MainWindow) -> None:
        main_window.tool_manager.activate("text")
        options_first = focusable_controls(main_window._tool_options)[0]  # noqa: SLF001
        palette_first = focusable_controls(main_window._toolbar)[0]  # noqa: SLF001
        w = options_first
        for _ in range(500):
            w = w.nextInFocusChain()
            if w is palette_first:
                break
        assert w is palette_first


class TestFocusOutline:
    @pytest.mark.parametrize("name", ["light", "dark"])
    def test_style_sheets_outline_every_control_kind(self, name: str) -> None:
        text = (tm.THEMES_DIR / f"{name}.qss").read_text(encoding="utf-8")
        for selector in (
            "QToolButton:focus",
            "QListView:focus",
            "QTreeView:focus",
            "QGraphicsView:focus",
            "QTabBar::tab:focus",
            "QCheckBox:focus",
            "QRadioButton:focus",
            "QSlider:focus",
            "QPushButton:focus",
            "QLineEdit:focus",
        ):
            match = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", text)
            assert match is not None, selector
            assert "2px solid @accent" in match.group(1), selector


def _luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def contrast_ratio(a: QColor, b: QColor) -> float:
    """WCAG 2.1 contrast ratio between two opaque colours."""
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# Text colour on the backgrounds it is drawn over (Section 13 tables and the chrome).
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("text_primary", "window_bg"),
    ("text_primary", "panel_bg"),
    ("text_primary", "toolbar_bg"),
    ("text_primary", "button_hover"),
    ("text_primary", "button_pressed"),
    ("text_primary", "input_bg"),
    ("text_primary", "tooltip_bg"),
    ("text_secondary", "window_bg"),
    ("text_secondary", "panel_bg"),
    ("accent_text", "accent"),
    ("accent", "window_bg"),
    ("error", "window_bg"),
    ("error", "toolbar_bg"),
    ("warning", "window_bg"),
    ("warning", "toolbar_bg"),
    ("ruler_text", "ruler_bg"),
    ("empty_canvas_text", "panel_bg"),
)


class TestContrast:
    def test_ratio_of_black_on_white(self) -> None:
        assert contrast_ratio(QColor("#000000"), QColor("#FFFFFF")) == pytest.approx(21.0)

    @pytest.mark.parametrize("name", ["light", "dark"])
    def test_text_pairs_meet_aa(self, name: str) -> None:
        colors = load_theme(name).colors
        failures = []
        for fg, bg in TEXT_PAIRS:
            ratio = contrast_ratio(getattr(colors, fg), getattr(colors, bg))
            if ratio < 4.5:
                failures.append(f"{name}: {fg} on {bg} = {ratio:.2f}")
        assert failures == []

    def test_light_theme_file_is_the_one_measured(self) -> None:
        assert (tm.THEMES_DIR / "light.qss").is_file()
        assert Path(tm.THEMES_DIR / "dark.qss").is_file()


class TestStatusAnnouncements:
    def test_hint_zone_is_a_live_label(self, main_window: MainWindow) -> None:
        bar = main_window._status_bar  # noqa: SLF001
        label = bar._hint_label  # noqa: SLF001
        # No accessible name of its own: Qt reports each text change as a name change,
        # which is what a screen reader announces.
        assert label.accessibleName() == ""
        assert label.accessibleDescription() == "Status message"
        bar.set_hint("Exported shot.png")
        assert label.text() == "Exported shot.png"
        assert label.accessibleName() == ""
