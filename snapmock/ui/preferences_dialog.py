"""PreferencesDialog — sidebar categories over every persistent setting (General UI PRD 11.3).

The left sidebar lists the categories; the right side shows one page at a
time. Every control reads its value from :class:`AppSettings` at construction
and :meth:`get_changes` reports what the user changed, keyed by setting name,
so the main window can persist each change and apply it live. No control is
ever disabled (PRD 1.3): dependent settings stay editable and take effect when
their parent setting allows.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from snapmock.capture.models import (
    HOTKEY_ACTION_FULL_SCREEN,
    HOTKEY_ACTION_REGION,
    HOTKEY_ACTION_WINDOW,
    CaptureMode,
    FullScreenScope,
)
from snapmock.config.constants import (
    APP_NAME,
    LIBRARY_THUMBNAIL_MAX,
    LIBRARY_THUMBNAIL_MIN,
    PANEL_THRESHOLD_MAX,
    PANEL_THRESHOLD_MIN,
)
from snapmock.config.packaging import capture_command
from snapmock.config.settings import AppSettings
from snapmock.core.theme_manager import current_theme
from snapmock.library.model import SORT_OPTIONS
from snapmock.ui.accessibility import apply_default_names
from snapmock.ui.color_picker import ColorPicker

if TYPE_CHECKING:
    from snapmock.capture.manager import CaptureManager

HOTKEY_IN_USE = "In use by another application"
CURSOR_UNAVAILABLE = "Not available on this desktop"
CAPTURE_MODE_FOR_ACTION = {
    HOTKEY_ACTION_REGION: "region",
    HOTKEY_ACTION_WINDOW: "window",
    HOTKEY_ACTION_FULL_SCREEN: "full",
}


def command_line_for_action(action: str) -> str:
    """The command that takes *action*'s capture in the form this process runs as.

    Read at call time, never stored: the AppImage's path and the Flatpak's
    ``flatpak run`` line differ from the checkout's (``config/packaging.py``).
    """
    return capture_command(CAPTURE_MODE_FOR_ACTION[action])


HOTKEY_LABELS = {
    HOTKEY_ACTION_REGION: "Region hotkey:",
    HOTKEY_ACTION_WINDOW: "Active window hotkey:",
    HOTKEY_ACTION_FULL_SCREEN: "Full screen hotkey:",
}

CATEGORY_GENERAL = "General"
CATEGORY_APPEARANCE = "Appearance"
CATEGORY_CANVAS = "Canvas & Grid"
CATEGORY_TOOLS = "Tools"
CATEGORY_LIBRARY = "Library"
CATEGORY_CAPTURE = "Capture"
CATEGORY_PERFORMANCE = "Performance"

THEME_CHOICES = (("Light", "light"), ("Dark", "dark"), ("System", "system"))
ICON_SIZE_CHOICES = (("Small (16 px)", 16), ("Medium (24 px)", 24), ("Large (32 px)", 32))
CHECKERBOARD_CHOICES = (("Small (4 px)", 4), ("Medium (8 px)", 8), ("Large (16 px)", 16))
UI_FONT_CHOICES = (("Small", "small"), ("Medium", "medium"), ("Large", "large"))
LANGUAGE_CHOICES = (("English", "en"),)


class _ThemeColorField(QWidget):
    """A colour swatch with a "Follow theme" checkbox; value() is None while following."""

    def __init__(self, value: QColor | None, theme_value: QColor, label: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._theme_value = QColor(theme_value)
        self._picker = ColorPicker(
            value if value is not None else theme_value, allow_transparent=False
        )
        self._follow = QCheckBox(label)
        self._follow.setChecked(value is None)
        layout.addWidget(self._picker)
        layout.addWidget(self._follow)
        layout.addStretch(1)

    def value(self) -> QColor | None:
        return None if self._follow.isChecked() else QColor(self._picker.color)

    def set_value(self, value: QColor | None) -> None:
        self._follow.setChecked(value is None)
        self._picker.color = value if value is not None else self._theme_value


def _slider_with_value(low: int, high: int, value: int, suffix: str) -> tuple[QWidget, QSlider]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(low, high)
    slider.setValue(value)
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setSuffix(suffix)
    spin.setValue(value)
    slider.valueChanged.connect(spin.setValue)
    spin.valueChanged.connect(slider.setValue)
    layout.addWidget(slider, 1)
    layout.addWidget(spin)
    return row, slider


def _combo(choices: tuple[tuple[str, object], ...], current: object) -> QComboBox:
    combo = QComboBox()
    for label, data in choices:
        combo.addItem(label, data)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    return combo


class PreferencesDialog(QDialog):
    """Modal dialog for viewing and editing application preferences."""

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        capture: CaptureManager | None = None,
        active_theme: str = "Default",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(720, 480)
        self._settings = settings
        self._active_theme = active_theme
        self._capture = capture
        self._hotkey_edits: dict[str, QKeySequenceEdit] = {}
        self._hotkey_status: dict[str, QLabel] = {}
        # Setting name -> reader of the control's current value.
        self._readers: dict[str, Callable[[], object]] = {}
        self._pages: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(150)
        self._sidebar.setAccessibleName("Preference categories")
        self._stack = QStackedWidget()
        body.addWidget(self._sidebar)
        body.addWidget(self._stack, 1)
        outer.addLayout(body, 1)

        self._add_page(CATEGORY_GENERAL, self._build_general_page())
        self._add_page(CATEGORY_APPEARANCE, self._build_appearance_page())
        self._add_page(CATEGORY_CANVAS, self._build_canvas_page())
        self._add_page(CATEGORY_TOOLS, self._build_tools_page())
        self._add_page(CATEGORY_LIBRARY, self._build_library_page())
        self._capture_group: QWidget | None = None
        if capture is not None:
            self._capture_group = self._build_capture_page(capture)
            self._add_page(CATEGORY_CAPTURE, self._capture_group)
        self._add_page(CATEGORY_PERFORMANCE, self._build_performance_page())

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

        # Snapshot the original values so get_changes reports only real edits.
        self._orig: dict[str, Any] = {key: read() for key, read in self._readers.items()}

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # --- pages ---
        apply_default_names(self)

    def _add_page(self, title: str, page: QWidget) -> None:
        self._pages[title] = page
        self._sidebar.addItem(title)
        self._stack.addWidget(page)

    def show_category(self, title: str) -> None:
        """Bring one category into view."""
        for row in range(self._sidebar.count()):
            item = self._sidebar.item(row)
            if item is not None and item.text() == title:
                self._sidebar.setCurrentRow(row)
                return

    def focus_library_section(self) -> None:
        """Bring the Library settings into view (Library > Library Preferences…)."""
        self.show_category(CATEGORY_LIBRARY)
        self._library_dir_edit.setFocus()

    def focus_capture_section(self) -> None:
        """Bring the Capture settings into view (Capture > Capture Preferences…)."""
        if self._capture_group is not None:
            self.show_category(CATEGORY_CAPTURE)
            self._capture_mode_combo.setFocus()

    @staticmethod
    def _page() -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        form = QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return page, form

    def _build_general_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()

        self._language_combo = _combo(LANGUAGE_CHOICES, s.language())
        form.addRow("Language:", self._language_combo)
        self._readers["language"] = self._language_combo.currentData

        self._autosave_interval_spin = QSpinBox()
        self._autosave_interval_spin.setRange(0, 30)
        self._autosave_interval_spin.setSuffix(" min")
        self._autosave_interval_spin.setSpecialValueText("Disabled")
        self._autosave_interval_spin.setValue(
            s.autosave_interval_minutes() if s.autosave_enabled() else 0
        )
        form.addRow("Auto-save interval:", self._autosave_interval_spin)
        self._readers["autosave_interval"] = self._autosave_interval_spin.value

        self._recent_count_spin = QSpinBox()
        self._recent_count_spin.setRange(1, 20)
        self._recent_count_spin.setValue(s.recent_files_count())
        form.addRow("Recent files count:", self._recent_count_spin)
        self._readers["recent_files_count"] = self._recent_count_spin.value

        width, height = s.default_canvas_size()
        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_width_spin = QSpinBox()
        self._canvas_width_spin.setRange(1, 20000)
        self._canvas_width_spin.setSuffix(" px")
        self._canvas_width_spin.setValue(width)
        self._canvas_height_spin = QSpinBox()
        self._canvas_height_spin.setRange(1, 20000)
        self._canvas_height_spin.setSuffix(" px")
        self._canvas_height_spin.setValue(height)
        size_layout.addWidget(self._canvas_width_spin)
        size_layout.addWidget(QLabel("×"))
        size_layout.addWidget(self._canvas_height_spin)
        size_layout.addStretch(1)
        form.addRow("Default canvas size:", size_row)
        self._readers["default_canvas_size"] = lambda: (
            self._canvas_width_spin.value(),
            self._canvas_height_spin.value(),
        )

        self._canvas_color = ColorPicker(s.default_canvas_color(), allow_transparent=True)
        form.addRow("Default canvas color:", self._canvas_color)
        self._readers["default_canvas_color"] = lambda: QColor(self._canvas_color.color)

        self._pasteboard_field = _ThemeColorField(
            s.pasteboard_color(), current_theme().pasteboard, "Follow theme"
        )
        form.addRow("Default pasteboard color:", self._pasteboard_field)
        self._readers["pasteboard_color"] = self._pasteboard_field.value

        self._confirm_delete_cb = QCheckBox()
        self._confirm_delete_cb.setChecked(s.confirm_delete_layers())
        form.addRow("Confirm before deleting layers:", self._confirm_delete_cb)
        self._readers["confirm_delete_layers"] = self._confirm_delete_cb.isChecked
        return page

    def _build_appearance_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()
        theme = current_theme()

        self._theme_combo = _combo(THEME_CHOICES, s.theme_mode())
        form.addRow("Theme:", self._theme_combo)
        self._readers["theme_mode"] = self._theme_combo.currentData

        self._icon_size_combo = _combo(ICON_SIZE_CHOICES, s.icon_size())
        form.addRow("Icon size:", self._icon_size_combo)
        self._readers["icon_size"] = self._icon_size_combo.currentData

        self._checkerboard_size_combo = _combo(CHECKERBOARD_CHOICES, s.checkerboard_size())
        form.addRow("Canvas checkerboard size:", self._checkerboard_size_combo)
        self._readers["checkerboard_size"] = self._checkerboard_size_combo.currentData

        colors = s.checkerboard_colors()
        self._checker_a = _ThemeColorField(
            colors[0] if colors else None, theme.checkerboard_a, "Follow theme"
        )
        self._checker_b = _ThemeColorField(
            colors[1] if colors else None, theme.checkerboard_b, "Follow theme"
        )
        form.addRow("Checkerboard color 1:", self._checker_a)
        form.addRow("Checkerboard color 2:", self._checker_b)
        self._readers["checkerboard_colors"] = self._checkerboard_colors

        self._ui_font_combo = _combo(UI_FONT_CHOICES, s.ui_font_size())
        form.addRow("UI font size:", self._ui_font_combo)
        self._readers["ui_font_size"] = self._ui_font_combo.currentData

        # Panel collapse thresholds (PRD 15.2): the window widths that narrow the
        # right panels and turn them into icon strips.
        self._narrow_threshold_spin = QSpinBox()
        self._narrow_threshold_spin.setRange(PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)
        self._narrow_threshold_spin.setSuffix(" px")
        self._narrow_threshold_spin.setValue(s.panel_narrow_threshold())
        form.addRow("Narrow panels below:", self._narrow_threshold_spin)
        self._readers["panel_narrow_threshold"] = self._narrow_threshold_spin.value
        self._strip_threshold_spin = QSpinBox()
        self._strip_threshold_spin.setRange(PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)
        self._strip_threshold_spin.setSuffix(" px")
        self._strip_threshold_spin.setValue(s.panel_strip_threshold())
        form.addRow("Icon-strip panels at or below:", self._strip_threshold_spin)
        self._readers["panel_strip_threshold"] = self._strip_threshold_spin.value
        return page

    def _checkerboard_colors(self) -> tuple[QColor, QColor] | None:
        a, b = self._checker_a.value(), self._checker_b.value()
        theme = current_theme()
        if a is None and b is None:
            return None
        return (a or theme.checkerboard_a, b or theme.checkerboard_b)

    def _build_canvas_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()

        self._grid_size_spin = QSpinBox()
        self._grid_size_spin.setRange(1, 100)
        self._grid_size_spin.setSuffix(" px")
        self._grid_size_spin.setValue(s.grid_size())
        form.addRow("Default grid size:", self._grid_size_spin)
        self._readers["grid_size"] = self._grid_size_spin.value

        theme_grid = QColor(current_theme().grid_lines)
        theme_grid.setAlpha(255)
        self._grid_color_field = _ThemeColorField(s.grid_color(), theme_grid, "Follow theme")
        form.addRow("Grid color:", self._grid_color_field)
        self._readers["grid_color"] = self._grid_color_field.value

        theme_opacity = round(current_theme().grid_lines.alpha() / 2.55)
        opacity = s.grid_opacity()
        row, self._grid_opacity_slider = _slider_with_value(
            1, 100, opacity if opacity is not None else theme_opacity, "%"
        )
        self._grid_opacity_follow = QCheckBox("Follow theme")
        self._grid_opacity_follow.setChecked(opacity is None)
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(row, 1)
        opacity_layout.addWidget(self._grid_opacity_follow)
        form.addRow("Grid opacity:", opacity_row)
        self._readers["grid_opacity"] = lambda: (
            None if self._grid_opacity_follow.isChecked() else self._grid_opacity_slider.value()
        )

        self._snap_tolerance_spin = QSpinBox()
        self._snap_tolerance_spin.setRange(1, 20)
        self._snap_tolerance_spin.setSuffix(" px")
        self._snap_tolerance_spin.setValue(s.snap_tolerance())
        form.addRow("Snap tolerance:", self._snap_tolerance_spin)
        self._readers["snap_tolerance"] = self._snap_tolerance_spin.value

        self._pixel_grid_spin = QSpinBox()
        self._pixel_grid_spin.setRange(100, 3200)
        self._pixel_grid_spin.setSingleStep(100)
        self._pixel_grid_spin.setSuffix("%")
        self._pixel_grid_spin.setValue(s.pixel_grid_zoom())
        form.addRow("Show pixel grid at zoom above:", self._pixel_grid_spin)
        self._readers["pixel_grid_zoom"] = self._pixel_grid_spin.value

        self._guide_color = ColorPicker(s.guide_color(), allow_transparent=False)
        form.addRow("Guide color:", self._guide_color)
        self._readers["guide_color"] = lambda: QColor(self._guide_color.color)

        row, self._guide_opacity_slider = _slider_with_value(1, 100, s.guide_opacity(), "%")
        form.addRow("Guide opacity:", row)
        self._readers["guide_opacity"] = self._guide_opacity_slider.value

        self._layer_hover_cb = QCheckBox()
        self._layer_hover_cb.setChecked(s.layer_hover_highlight())
        self._layer_hover_cb.setAccessibleName("Highlight layer items on hover")
        form.addRow("Highlight layer items on hover:", self._layer_hover_cb)
        self._readers["layer_hover_highlight"] = self._layer_hover_cb.isChecked
        return page

    def _build_tools_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()

        # Decision 7.2 (Phase 7): these values are the built-in Default tool theme's.
        note = QLabel(
            "These values define the built-in Default tool theme. "
            f"Active theme: {self._active_theme}."
        )
        note.setWordWrap(True)
        note.setObjectName("ToolsThemeNote")
        form.addRow(note)

        self._stroke_color = ColorPicker(s.default_stroke_color(), allow_transparent=False)
        form.addRow("Default stroke color:", self._stroke_color)
        self._readers["default_stroke_color"] = lambda: QColor(self._stroke_color.color)

        self._stroke_width_spin = QDoubleSpinBox()
        self._stroke_width_spin.setRange(0.0, 100.0)
        self._stroke_width_spin.setDecimals(1)
        self._stroke_width_spin.setSuffix(" px")
        self._stroke_width_spin.setValue(s.default_stroke_width())
        form.addRow("Default stroke width:", self._stroke_width_spin)
        self._readers["default_stroke_width"] = self._stroke_width_spin.value

        self._fill_color = ColorPicker(s.default_fill_color(), allow_transparent=True)
        form.addRow("Default fill color:", self._fill_color)
        self._readers["default_fill_color"] = lambda: QColor(self._fill_color.color)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont(s.default_font_family()))
        form.addRow("Default font:", self._font_combo)
        self._readers["default_font_family"] = lambda: self._font_combo.currentFont().family()

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(1, 500)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setValue(s.default_font_size())
        form.addRow("Default font size:", self._font_size_spin)
        self._readers["default_font_size"] = self._font_size_spin.value

        row, self._smoothing_slider = _slider_with_value(0, 100, s.freehand_smoothing(), "%")
        form.addRow("Freehand smoothing default:", row)
        self._readers["freehand_smoothing"] = self._smoothing_slider.value

        self._step_start_spin = QSpinBox()
        self._step_start_spin.setRange(0, 9999)
        self._step_start_spin.setValue(s.numbered_step_start())
        form.addRow("Numbered step starting number:", self._step_start_spin)
        self._readers["numbered_step_start"] = self._step_start_spin.value
        return page

    def _build_library_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()

        dir_row = QHBoxLayout()
        self._library_dir_edit = QLineEdit(str(s.library_directory()))
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_library_dir)
        dir_row.addWidget(self._library_dir_edit, 1)
        dir_row.addWidget(browse_btn)
        form.addRow("Library directory:", dir_row)
        self._readers["library_directory"] = lambda: self._library_dir_edit.text().strip()

        self._library_auto_open_cb = QCheckBox()
        self._library_auto_open_cb.setChecked(s.library_auto_open())
        form.addRow("Auto-open captures:", self._library_auto_open_cb)
        self._readers["library_auto_open"] = self._library_auto_open_cb.isChecked

        self._library_view_combo = _combo(
            (("Grid", "grid"), ("Preview (List)", "list")), s.library_default_view_mode()
        )
        form.addRow("Default view mode:", self._library_view_combo)
        self._readers["library_default_view_mode"] = self._library_view_combo.currentData

        row, self._library_thumb_slider = _slider_with_value(
            LIBRARY_THUMBNAIL_MIN, LIBRARY_THUMBNAIL_MAX, s.library_default_thumbnail_size(), " px"
        )
        form.addRow("Default thumbnail size:", row)
        self._readers["library_default_thumbnail_size"] = self._library_thumb_slider.value

        self._library_sort_combo = _combo(
            tuple((label, sort_id) for sort_id, label in SORT_OPTIONS), s.library_default_sort()
        )
        form.addRow("Default sort order:", self._library_sort_combo)
        self._readers["library_default_sort"] = self._library_sort_combo.currentData

        self._library_toast_cb = QCheckBox()
        self._library_toast_cb.setChecked(s.library_toast_enabled())
        form.addRow("Toast notifications:", self._library_toast_cb)
        self._readers["library_toast_enabled"] = self._library_toast_cb.isChecked
        return page

    def _build_performance_page(self) -> QWidget:
        s = self._settings
        page, form = self._page()

        self._undo_limit_spin = QSpinBox()
        self._undo_limit_spin.setRange(10, 1000)
        self._undo_limit_spin.setValue(s.undo_limit())
        form.addRow("Undo history limit:", self._undo_limit_spin)
        self._readers["undo_limit"] = self._undo_limit_spin.value

        self._thumbnail_delay_spin = QSpinBox()
        self._thumbnail_delay_spin.setRange(100, 2000)
        self._thumbnail_delay_spin.setSingleStep(50)
        self._thumbnail_delay_spin.setSuffix(" ms")
        self._thumbnail_delay_spin.setValue(s.thumbnail_delay_ms())
        form.addRow("Thumbnail update delay:", self._thumbnail_delay_spin)
        self._readers["thumbnail_delay_ms"] = self._thumbnail_delay_spin.value
        return page

    # --- Capture page (Screen Capture PRD 8.1, 6.7, 9.2, 9.3) ---

    def _build_capture_page(self, capture: CaptureManager) -> QWidget:
        s = self._settings
        page, form = self._page()
        caps = capture.capabilities

        self._capture_mode_combo = _combo(
            (
                ("Region", CaptureMode.REGION.value),
                ("Active window", CaptureMode.ACTIVE_WINDOW.value),
                ("Full screen", CaptureMode.FULL_SCREEN.value),
            ),
            s.capture_default_mode(),
        )
        form.addRow("Default capture mode:", self._capture_mode_combo)
        self._readers["capture_default_mode"] = self._capture_mode_combo.currentData

        hotkeys_supported = capture.hotkey_backend.supported
        for action in (HOTKEY_ACTION_REGION, HOTKEY_ACTION_WINDOW, HOTKEY_ACTION_FULL_SCREEN):
            if hotkeys_supported:
                form.addRow(HOTKEY_LABELS[action], self._build_hotkey_row(capture, action))
            else:
                form.addRow(HOTKEY_LABELS[action], self._build_command_row(action))
        if not hotkeys_supported:
            help_link = QLabel('<a href="#">How to set up a desktop shortcut...</a>')
            help_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            help_link.linkActivated.connect(lambda _href: self.show_desktop_shortcut_help())
            form.addRow("", help_link)
        else:
            conflicts = QLabel(
                "GNOME on X11 and Windows 11 with the Snipping Tool shortcut both claim "
                "PrintScreen by default."
            )
            conflicts.setWordWrap(True)
            conflicts.setProperty("role", "secondary")
            form.addRow("", conflicts)

        self._capture_delay_spin = QSpinBox()
        self._capture_delay_spin.setRange(0, 60)
        self._capture_delay_spin.setSuffix(" s")
        self._capture_delay_spin.setValue(s.capture_delay_seconds())
        form.addRow("Delay:", self._capture_delay_spin)
        self._readers["capture_delay_seconds"] = self._capture_delay_spin.value

        cursor_row = QHBoxLayout()
        self._capture_cursor_cb = QCheckBox()
        self._capture_cursor_cb.setChecked(s.capture_include_cursor())
        cursor_row.addWidget(self._capture_cursor_cb)
        if not caps.cursor:
            note = QLabel(CURSOR_UNAVAILABLE)
            note.setProperty("role", "secondary")
            cursor_row.addWidget(note)
        cursor_row.addStretch(1)
        form.addRow("Include mouse cursor:", cursor_row)
        self._readers["capture_include_cursor"] = self._capture_cursor_cb.isChecked

        self._capture_sound_cb = QCheckBox()
        self._capture_sound_cb.setChecked(s.capture_play_sound())
        form.addRow("Play capture sound:", self._capture_sound_cb)
        self._readers["capture_play_sound"] = self._capture_sound_cb.isChecked

        self._capture_hide_cb = QCheckBox()
        self._capture_hide_cb.setChecked(s.capture_hide_window())
        form.addRow(f"Hide {APP_NAME} window during capture:", self._capture_hide_cb)
        self._readers["capture_hide_window"] = self._capture_hide_cb.isChecked

        self._capture_clipboard_cb = QCheckBox()
        self._capture_clipboard_cb.setChecked(s.capture_copy_to_clipboard())
        form.addRow("Copy to clipboard:", self._capture_clipboard_cb)
        self._readers["capture_copy_to_clipboard"] = self._capture_clipboard_cb.isChecked

        self._capture_scope_combo = _combo(
            (
                ("Monitor under cursor", FullScreenScope.MONITOR_UNDER_CURSOR.value),
                ("All monitors", FullScreenScope.ALL_MONITORS.value),
            ),
            s.capture_full_screen_scope(),
        )
        form.addRow("Full screen scope:", self._capture_scope_combo)
        self._readers["capture_full_screen_scope"] = self._capture_scope_combo.currentData

        self._capture_magnifier_cb = QCheckBox()
        self._capture_magnifier_cb.setChecked(s.capture_show_magnifier())
        form.addRow("Show magnifier:", self._capture_magnifier_cb)
        self._readers["capture_show_magnifier"] = self._capture_magnifier_cb.isChecked

        self._capture_tray_cb = QCheckBox()
        self._capture_tray_cb.setChecked(s.capture_tray_enabled())
        form.addRow("Show tray icon:", self._capture_tray_cb)
        self._readers["capture_tray_enabled"] = self._capture_tray_cb.isChecked

        # Never disabled (General UI PRD 1.3): editable while the tray is off; it
        # takes effect once the tray icon is shown.
        self._capture_keep_running_cb = QCheckBox()
        self._capture_keep_running_cb.setChecked(s.capture_keep_running_in_tray())
        self._capture_keep_running_cb.setToolTip("Takes effect while the tray icon is shown")
        form.addRow("Keep running in tray when window is closed:", self._capture_keep_running_cb)
        self._readers["capture_keep_running_in_tray"] = self._capture_keep_running_cb.isChecked

        self._capability_label = QLabel(capture.capability_summary())
        self._capability_label.setWordWrap(True)
        self._capability_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._capability_label.setProperty("role", "secondary")
        form.addRow(self._capability_label)
        return page

    def _build_hotkey_row(self, capture: CaptureManager, action: str) -> QWidget:
        """A key sequence editor that registers on change (PRD 3.1, 9.3)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QKeySequenceEdit()
        edit.setMaximumSequenceLength(1)
        binding = capture.binding(action)
        if binding is not None:
            edit.setKeySequence(binding.key_sequence)
        status = QLabel("")
        status.setProperty("role", "error")
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self._change_hotkey(action, QKeySequence()))
        edit.editingFinished.connect(lambda: self._change_hotkey(action, edit.keySequence()))
        layout.addWidget(edit, 1)
        layout.addWidget(clear)
        layout.addWidget(status)
        self._hotkey_edits[action] = edit
        self._hotkey_status[action] = status
        self._refresh_hotkey_status(action)
        return row

    def _build_command_row(self, action: str) -> QWidget:
        """Command-line guidance with a Copy button (PRD 6.7, Wayland and macOS)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        command = command_line_for_action(action)
        field = QLineEdit(command)
        field.setReadOnly(True)
        field.setToolTip("Bind a desktop shortcut to this command")
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: self._copy_text(command))
        layout.addWidget(QLabel("Bind a desktop shortcut to:"))
        layout.addWidget(field, 1)
        layout.addWidget(copy)
        return row

    @staticmethod
    def _copy_text(text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _change_hotkey(self, action: str, sequence: QKeySequence) -> None:
        if self._capture is None:
            return
        text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        ok = self._capture.set_hotkey(action, text)
        binding = self._capture.binding(action)
        edit = self._hotkey_edits.get(action)
        if edit is not None and binding is not None:
            edit.blockSignals(True)
            edit.setKeySequence(binding.key_sequence)
            edit.blockSignals(False)
        self._refresh_hotkey_status(action, failed_now=not ok)

    def _refresh_hotkey_status(self, action: str, *, failed_now: bool = False) -> None:
        if self._capture is None:
            return
        binding = self._capture.binding(action)
        label = self._hotkey_status.get(action)
        if label is None or binding is None:
            return
        if failed_now or (binding.is_bound and not binding.registered):
            label.setText(HOTKEY_IN_USE)
        else:
            label.setText("")

    def hotkey_status_text(self, action: str) -> str:
        label = self._hotkey_status.get(action)
        return label.text() if label is not None else ""

    def show_desktop_shortcut_help(self) -> None:
        """The desktop-shortcut guidance (PRD 9.2), reachable at any time."""
        from snapmock.capture.onboarding import WaylandOnboardingDialog

        dlg = WaylandOnboardingDialog(self, help_only=True)
        dlg.exec()
        dlg.deleteLater()

    def _browse_library_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Library Directory", self._library_dir_edit.text()
        )
        if chosen:
            self._library_dir_edit.setText(str(Path(chosen)))

    # --- results ---

    def get_changes(self) -> dict[str, tuple[object, object]]:
        """Return only settings that actually changed, as ``(old_value, new_value)``."""
        changes: dict[str, tuple[object, object]] = {}
        for key, read in self._readers.items():
            new_value = read()
            if new_value != self._orig[key]:
                changes[key] = (self._orig[key], new_value)
        return changes
