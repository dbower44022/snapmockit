"""Persistent application settings backed by QSettings."""

import json
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

from snapmock.config.constants import (
    CHECKERBOARD_CELL_SIZE,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    DEFAULT_FILL_COLOR,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_STROKE_COLOR,
    DEFAULT_STROKE_WIDTH,
    GRID_SIZE_DEFAULT,
    GUIDE_COLOR_DEFAULT,
    GUIDE_OPACITY_DEFAULT,
    LIBRARY_PREVIEW_DEFAULT,
    LIBRARY_THUMBNAIL_DEFAULT,
    PANEL_NARROW_THRESHOLD_DEFAULT,
    PANEL_STRIP_THRESHOLD_DEFAULT,
    PANEL_THRESHOLD_MAX,
    PANEL_THRESHOLD_MIN,
    RECENT_COLORS_MAX,
    RECENT_FILES_DEFAULT,
    RECENT_ZOOM_MAX,
    SNAP_TOLERANCE_DEFAULT,
    THUMBNAIL_DELAY_DEFAULT_MS,
    UNDO_LIMIT,
    ZOOM_DEFAULT,
    ZOOM_PIXEL_GRID_THRESHOLD,
)
from snapmock.config.migration import default_library_directory, storage_names

# Global hotkey settings: action -> (settings key, default portable key sequence).
CAPTURE_HOTKEY_KEYS: dict[str, tuple[str, str]] = {
    "capture.region": ("capture/hotkeyRegion", "Print"),
    "capture.window": ("capture/hotkeyWindow", "Alt+Print"),
    "capture.full_screen": ("capture/hotkeyFullScreen", "Ctrl+Print"),
}


class AppSettings:
    """Thin wrapper around QSettings for typed access to application preferences."""

    def __init__(self) -> None:
        org, app = storage_names()
        self._qs = QSettings(org, app)

    # --- window geometry ---

    def save_window_geometry(self, geometry: bytes) -> None:
        self._qs.setValue("window/geometry", geometry)

    def window_geometry(self) -> bytes | None:
        val = self._qs.value("window/geometry")
        if isinstance(val, bytes):
            return val
        return None

    def save_window_state(self, state: bytes) -> None:
        self._qs.setValue("window/state", state)

    def window_state(self) -> bytes | None:
        val = self._qs.value("window/state")
        if isinstance(val, bytes):
            return val
        return None

    # --- recent files ---

    def recent_files(self) -> list[str]:
        val = self._qs.value("files/recent", [])
        if isinstance(val, list):
            return [str(v) for v in val]
        return []

    def set_recent_files(self, paths: list[str]) -> None:
        self._qs.setValue("files/recent", paths)

    # Zoom per recently opened project (General UI PRD 15.4): the metadata beside
    # each recent path, newest first, capped so the map cannot grow without bound.

    def _recent_zoom_map(self) -> dict[str, int]:
        raw = self._qs.value("files/recentZoom", "")
        if not isinstance(raw, str) or not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items() if isinstance(v, int | float)}

    def recent_file_zoom(self, path: Path) -> int | None:
        """The zoom percentage the project at *path* was last viewed at, if recorded."""
        return self._recent_zoom_map().get(str(path.resolve()))

    def set_recent_file_zoom(self, path: Path, zoom: int) -> None:
        key = str(path.resolve())
        rest = {k: v for k, v in self._recent_zoom_map().items() if k != key}
        entries = [(key, int(zoom)), *rest.items()][:RECENT_ZOOM_MAX]
        self._qs.setValue("files/recentZoom", json.dumps(dict(entries)))

    # --- view preferences ---

    def grid_size(self) -> int:
        val = self._qs.value("view/gridSize", GRID_SIZE_DEFAULT)
        return int(val)

    def set_grid_size(self, size: int) -> None:
        self._qs.setValue("view/gridSize", size)

    def grid_visible(self) -> bool:
        return bool(self._qs.value("view/gridVisible", False))

    def set_grid_visible(self, visible: bool) -> None:
        self._qs.setValue("view/gridVisible", visible)

    def zoom_level(self) -> int:
        val = self._qs.value("view/zoomLevel", ZOOM_DEFAULT)
        return int(val)

    def set_zoom_level(self, level: int) -> None:
        self._qs.setValue("view/zoomLevel", level)

    def rulers_visible(self) -> bool:
        return bool(self._qs.value("view/rulersVisible", False))

    def set_rulers_visible(self, visible: bool) -> None:
        self._qs.setValue("view/rulersVisible", visible)

    def crosshairs_visible(self) -> bool:
        """View > Show Crosshairs (General UI PRD 3.3, 15.4)."""
        return _as_bool(self._qs.value("view/crosshairsVisible", False))

    def set_crosshairs_visible(self, visible: bool) -> None:
        self._qs.setValue("view/crosshairsVisible", visible)

    def guides_visible(self) -> bool:
        """View > Show Guides (General UI PRD 3.3); guides stay in place when hidden."""
        return _as_bool(self._qs.value("view/guidesVisible", True))

    def set_guides_visible(self, visible: bool) -> None:
        self._qs.setValue("view/guidesVisible", visible)

    def snap_to_guides(self) -> bool:
        return _as_bool(self._qs.value("view/snapToGuides", False))

    def set_snap_to_guides(self, enabled: bool) -> None:
        self._qs.setValue("view/snapToGuides", enabled)

    def guides_locked(self) -> bool:
        return _as_bool(self._qs.value("view/guidesLocked", False))

    def set_guides_locked(self, locked: bool) -> None:
        self._qs.setValue("view/guidesLocked", locked)

    def snap_to_grid(self) -> bool:
        return bool(self._qs.value("view/snapToGrid", False))

    def set_snap_to_grid(self, enabled: bool) -> None:
        self._qs.setValue("view/snapToGrid", enabled)

    # --- colour picker swatches (General UI PRD 11.1) ---

    def recent_colors(self) -> list[QColor]:
        """The last twelve colours committed in a picker, newest first."""
        val = self._qs.value("colors/recent", [])
        if not isinstance(val, list):
            return []
        colors = [_optional_color(v) for v in val]
        return [c for c in colors if c is not None][:RECENT_COLORS_MAX]

    def push_recent_color(self, color: QColor) -> None:
        """Put *color* first, dropping an earlier copy of the same colour and the excess."""
        key = _color_text(color)
        rest = [c for c in self.recent_colors() if _color_text(c) != key]
        self._qs.setValue(
            "colors/recent", [key] + [_color_text(c) for c in rest][: RECENT_COLORS_MAX - 1]
        )

    def saved_colors(self) -> list[QColor | None]:
        """The twelve saved slots; None for an empty slot."""
        val = self._qs.value("colors/saved", [])
        slots: list[QColor | None] = [None] * RECENT_COLORS_MAX
        if isinstance(val, list):
            for i, v in enumerate(val[:RECENT_COLORS_MAX]):
                slots[i] = _optional_color(v)
        return slots

    def set_saved_color(self, index: int, color: QColor | None) -> None:
        slots = self.saved_colors()
        if 0 <= index < RECENT_COLORS_MAX:
            slots[index] = QColor(color) if color is not None else None
        self._qs.setValue("colors/saved", [_color_text(c) for c in slots])

    def property_section_expanded(self, title: str) -> bool:
        """Whether a Property Panel section is expanded (PRD 8.2); expanded by default."""
        key = "panels/propertySection/" + "".join(c for c in title if c.isalnum())
        return _as_bool(self._qs.value(key, True))

    def set_property_section_expanded(self, title: str, expanded: bool) -> None:
        key = "panels/propertySection/" + "".join(c for c in title if c.isalnum())
        self._qs.setValue(key, expanded)

    def layer_hover_highlight(self) -> bool:
        """Hovering a Layer Panel row outlines that layer's items (General UI PRD 7.3)."""
        return _as_bool(self._qs.value("view/layerHoverHighlight", True))

    def set_layer_hover_highlight(self, enabled: bool) -> None:
        self._qs.setValue("view/layerHoverHighlight", enabled)

    def status_bar_visible(self) -> bool:
        return _as_bool(self._qs.value("view/statusBarVisible", True))

    def set_status_bar_visible(self, visible: bool) -> None:
        self._qs.setValue("view/statusBarVisible", visible)

    # --- first run and the Welcome panel (General UI PRD 16) ---

    def first_run_done(self) -> bool:
        """Whether the first launch has applied the Section 16.2 defaults."""
        return _as_bool(self._qs.value("general/firstRunDone", False))

    def set_first_run_done(self, done: bool) -> None:
        self._qs.setValue("general/firstRunDone", done)

    def show_welcome_at_startup(self) -> bool:
        """Whether the Welcome panel opens at launch; the first run turns it on and
        the panel's "Don't show this again" checkbox turns it off."""
        return _as_bool(self._qs.value("welcome/showAtStartup", False))

    def set_show_welcome_at_startup(self, show: bool) -> None:
        self._qs.setValue("welcome/showAtStartup", show)

    # --- panel collapse thresholds (General UI PRD 15.2) ---

    def panel_narrow_threshold(self) -> int:
        """Window width below which the right panels go narrow."""
        val = int(self._qs.value("panels/narrowThreshold", PANEL_NARROW_THRESHOLD_DEFAULT))
        return _clamp(val, PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)

    def set_panel_narrow_threshold(self, width: int) -> None:
        self._qs.setValue(
            "panels/narrowThreshold", _clamp(width, PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)
        )

    def panel_strip_threshold(self) -> int:
        """Window width at or below which the right panels become icon strips."""
        val = int(self._qs.value("panels/stripThreshold", PANEL_STRIP_THRESHOLD_DEFAULT))
        return _clamp(val, PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)

    def set_panel_strip_threshold(self, width: int) -> None:
        self._qs.setValue(
            "panels/stripThreshold", _clamp(width, PANEL_THRESHOLD_MIN, PANEL_THRESHOLD_MAX)
        )

    # --- general (General UI PRD 11.3 General) ---

    def language(self) -> str:
        return str(self._qs.value("general/language", "en"))

    def set_language(self, code: str) -> None:
        self._qs.setValue("general/language", code)

    def recent_files_count(self) -> int:
        return _clamp(int(self._qs.value("files/recentCount", RECENT_FILES_DEFAULT)), 1, 20)

    def set_recent_files_count(self, count: int) -> None:
        self._qs.setValue("files/recentCount", _clamp(count, 1, 20))

    def default_canvas_size(self) -> tuple[int, int]:
        width = int(self._qs.value("canvas/defaultWidth", DEFAULT_CANVAS_WIDTH))
        height = int(self._qs.value("canvas/defaultHeight", DEFAULT_CANVAS_HEIGHT))
        return max(1, width), max(1, height)

    def set_default_canvas_size(self, width: int, height: int) -> None:
        self._qs.setValue("canvas/defaultWidth", max(1, width))
        self._qs.setValue("canvas/defaultHeight", max(1, height))

    def default_canvas_color(self) -> QColor:
        return _color(self._qs.value("canvas/defaultColor", "#FFFFFF"), "#FFFFFF")

    def set_default_canvas_color(self, color: QColor) -> None:
        self._qs.setValue("canvas/defaultColor", _color_text(color))

    def pasteboard_color(self) -> QColor | None:
        """The pasteboard colour override, or None to follow the theme (PRD 13)."""
        return _optional_color(self._qs.value("canvas/pasteboardColor", ""))

    def set_pasteboard_color(self, color: QColor | None) -> None:
        self._qs.setValue("canvas/pasteboardColor", _color_text(color) if color else "")

    def confirm_delete_layers(self) -> bool:
        return _as_bool(self._qs.value("general/confirmDeleteLayers", True))

    def set_confirm_delete_layers(self, enabled: bool) -> None:
        self._qs.setValue("general/confirmDeleteLayers", enabled)

    # --- appearance (General UI PRD 11.3 Appearance, 13.1, 15.4) ---

    def checkerboard_size(self) -> int:
        val = int(self._qs.value("appearance/checkerboardSize", CHECKERBOARD_CELL_SIZE))
        return val if val in (4, 8, 16) else CHECKERBOARD_CELL_SIZE

    def set_checkerboard_size(self, size: int) -> None:
        self._qs.setValue("appearance/checkerboardSize", size)

    def checkerboard_colors(self) -> tuple[QColor, QColor] | None:
        """The two checkerboard colours, or None to follow the theme."""
        a = _optional_color(self._qs.value("appearance/checkerboardColorA", ""))
        b = _optional_color(self._qs.value("appearance/checkerboardColorB", ""))
        if a is None or b is None:
            return None
        return a, b

    def set_checkerboard_colors(self, colors: tuple[QColor, QColor] | None) -> None:
        a = _color_text(colors[0]) if colors else ""
        b = _color_text(colors[1]) if colors else ""
        self._qs.setValue("appearance/checkerboardColorA", a)
        self._qs.setValue("appearance/checkerboardColorB", b)

    # --- canvas and grid (General UI PRD 11.3 Canvas & Grid) ---

    def grid_color(self) -> QColor | None:
        """The grid colour override, or None to follow the theme."""
        return _optional_color(self._qs.value("view/gridColor", ""))

    def set_grid_color(self, color: QColor | None) -> None:
        self._qs.setValue("view/gridColor", _color_text(color) if color else "")

    def grid_opacity(self) -> int | None:
        """Grid opacity in percent, or None to follow the theme."""
        val = self._qs.value("view/gridOpacity", "")
        if val is None or val == "":
            return None
        return _clamp(int(val), 1, 100)

    def set_grid_opacity(self, percent: int | None) -> None:
        self._qs.setValue("view/gridOpacity", _clamp(percent, 1, 100) if percent else "")

    def snap_tolerance(self) -> int:
        return _clamp(int(self._qs.value("view/snapTolerance", SNAP_TOLERANCE_DEFAULT)), 1, 20)

    def set_snap_tolerance(self, pixels: int) -> None:
        self._qs.setValue("view/snapTolerance", _clamp(pixels, 1, 20))

    def pixel_grid_zoom(self) -> int:
        val = int(self._qs.value("view/pixelGridZoom", ZOOM_PIXEL_GRID_THRESHOLD))
        return _clamp(val, 100, 3200)

    def set_pixel_grid_zoom(self, percent: int) -> None:
        self._qs.setValue("view/pixelGridZoom", _clamp(percent, 100, 3200))

    def guide_color(self) -> QColor:
        return _color(self._qs.value("view/guideColor", GUIDE_COLOR_DEFAULT), GUIDE_COLOR_DEFAULT)

    def set_guide_color(self, color: QColor) -> None:
        self._qs.setValue("view/guideColor", _color_text(color))

    def guide_opacity(self) -> int:
        return _clamp(int(self._qs.value("view/guideOpacity", GUIDE_OPACITY_DEFAULT)), 1, 100)

    def set_guide_opacity(self, percent: int) -> None:
        self._qs.setValue("view/guideOpacity", _clamp(percent, 1, 100))

    # --- tools (General UI PRD 11.3 Tools): defaults pushed into each tool ---

    def default_stroke_color(self) -> QColor:
        return _color(
            self._qs.value("tools/strokeColor", DEFAULT_STROKE_COLOR), DEFAULT_STROKE_COLOR
        )

    def set_default_stroke_color(self, color: QColor) -> None:
        self._qs.setValue("tools/strokeColor", _color_text(color))

    def default_stroke_width(self) -> float:
        return max(0.0, float(self._qs.value("tools/strokeWidth", DEFAULT_STROKE_WIDTH)))

    def set_default_stroke_width(self, width: float) -> None:
        self._qs.setValue("tools/strokeWidth", max(0.0, width))

    def default_fill_color(self) -> QColor:
        return _color(self._qs.value("tools/fillColor", DEFAULT_FILL_COLOR), DEFAULT_FILL_COLOR)

    def set_default_fill_color(self, color: QColor) -> None:
        self._qs.setValue("tools/fillColor", _color_text(color))

    def default_font_family(self) -> str:
        return str(self._qs.value("tools/fontFamily", DEFAULT_FONT_FAMILY)) or DEFAULT_FONT_FAMILY

    def set_default_font_family(self, family: str) -> None:
        self._qs.setValue("tools/fontFamily", family)

    def default_font_size(self) -> int:
        return max(1, int(self._qs.value("tools/fontSize", DEFAULT_FONT_SIZE)))

    def set_default_font_size(self, size: int) -> None:
        self._qs.setValue("tools/fontSize", max(1, size))

    def freehand_smoothing(self) -> int:
        return _clamp(int(self._qs.value("tools/freehandSmoothing", 50)), 0, 100)

    def set_freehand_smoothing(self, percent: int) -> None:
        self._qs.setValue("tools/freehandSmoothing", _clamp(percent, 0, 100))

    def numbered_step_start(self) -> int:
        return max(0, int(self._qs.value("tools/numberedStepStart", 1)))

    def set_numbered_step_start(self, number: int) -> None:
        self._qs.setValue("tools/numberedStepStart", max(0, number))

    # --- tool themes (General UI PRD 11.8): the active theme's name ---

    def active_tool_theme(self) -> str:
        return str(self._qs.value("tools/activeTheme", "Default")) or "Default"

    def set_active_tool_theme(self, name: str) -> None:
        self._qs.setValue("tools/activeTheme", name)

    # --- performance (General UI PRD 11.3 Performance) ---

    def undo_limit(self) -> int:
        return _clamp(int(self._qs.value("performance/undoLimit", UNDO_LIMIT)), 10, 1000)

    def set_undo_limit(self, limit: int) -> None:
        self._qs.setValue("performance/undoLimit", _clamp(limit, 10, 1000))

    def thumbnail_delay_ms(self) -> int:
        val = int(self._qs.value("performance/thumbnailDelayMs", THUMBNAIL_DELAY_DEFAULT_MS))
        return _clamp(val, 100, 2000)

    def set_thumbnail_delay_ms(self, delay: int) -> None:
        self._qs.setValue("performance/thumbnailDelayMs", _clamp(delay, 100, 2000))

    def theme_mode(self) -> str:
        """``light`` (the default), ``dark``, or ``system``."""
        val = str(self._qs.value("appearance/theme", "light"))
        return val if val in ("light", "dark", "system") else "light"

    def set_theme_mode(self, mode: str) -> None:
        self._qs.setValue("appearance/theme", mode)

    def icon_size(self) -> int:
        val = int(self._qs.value("appearance/iconSize", 24))
        return val if val in (16, 24, 32) else 24

    def set_icon_size(self, size: int) -> None:
        self._qs.setValue("appearance/iconSize", size)

    def ui_font_size(self) -> str:
        val = str(self._qs.value("appearance/uiFontSize", "medium"))
        return val if val in ("small", "medium", "large") else "medium"

    def set_ui_font_size(self, size: str) -> None:
        self._qs.setValue("appearance/uiFontSize", size)

    def last_tool(self) -> str:
        return str(self._qs.value("session/lastTool", ""))

    def set_last_tool(self, tool_id: str) -> None:
        self._qs.setValue("session/lastTool", tool_id)

    # --- export (General UI PRD 11.2, 15.4: last-used settings and directory per format) ---

    def export_settings(self, fmt: str) -> dict[str, object] | None:
        """The last-used Export dialog options for *fmt*, or None before the first export."""
        raw = self._qs.value(f"export/{fmt}/settings", "")
        if not isinstance(raw, str) or not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def set_export_settings(self, fmt: str, data: dict[str, object]) -> None:
        self._qs.setValue(f"export/{fmt}/settings", json.dumps(data))

    def export_last_directory(self, fmt: str) -> Path | None:
        val = self._qs.value(f"export/{fmt}/lastDirectory", "")
        if isinstance(val, str) and val:
            return Path(val)
        return None

    def set_export_last_directory(self, fmt: str, path: Path) -> None:
        self._qs.setValue(f"export/{fmt}/lastDirectory", str(path))

    def export_last_format(self) -> str:
        return str(self._qs.value("export/lastFormat", "png"))

    def set_export_last_format(self, fmt: str) -> None:
        self._qs.setValue("export/lastFormat", fmt)

    # --- autosave ---

    def autosave_enabled(self) -> bool:
        return bool(self._qs.value("autosave/enabled", True))

    def set_autosave_enabled(self, enabled: bool) -> None:
        self._qs.setValue("autosave/enabled", enabled)

    def autosave_interval_minutes(self) -> int:
        val = self._qs.value("autosave/interval", 2)
        return int(val)

    def set_autosave_interval_minutes(self, minutes: int) -> None:
        self._qs.setValue("autosave/interval", minutes)

    # --- library ---

    def library_directory(self) -> Path:
        val = self._qs.value("library/directory", "")
        if isinstance(val, str) and val:
            return Path(val)
        return default_library_directory()

    def set_library_directory(self, path: Path) -> None:
        self._qs.setValue("library/directory", str(path))

    def library_auto_open(self) -> bool:
        return _as_bool(self._qs.value("library/autoOpenCaptures", True))

    def set_library_auto_open(self, enabled: bool) -> None:
        self._qs.setValue("library/autoOpenCaptures", enabled)

    def library_toast_enabled(self) -> bool:
        return _as_bool(self._qs.value("library/toastNotifications", True))

    def set_library_toast_enabled(self, enabled: bool) -> None:
        self._qs.setValue("library/toastNotifications", enabled)

    def library_default_view_mode(self) -> str:
        val = self._qs.value("library/defaultViewMode", "grid")
        return "list" if str(val) == "list" else "grid"

    def set_library_default_view_mode(self, mode: str) -> None:
        self._qs.setValue("library/defaultViewMode", mode)

    def library_default_thumbnail_size(self) -> int:
        return int(self._qs.value("library/defaultThumbnailSize", LIBRARY_THUMBNAIL_DEFAULT))

    def set_library_default_thumbnail_size(self, size: int) -> None:
        self._qs.setValue("library/defaultThumbnailSize", size)

    def library_default_sort(self) -> str:
        return str(self._qs.value("library/defaultSort", "date_modified_desc"))

    def set_library_default_sort(self, sort_id: str) -> None:
        self._qs.setValue("library/defaultSort", sort_id)

    # panel state (current session values, restored on launch)

    def library_view_mode(self) -> str:
        val = self._qs.value("library/viewMode", self.library_default_view_mode())
        return "list" if str(val) == "list" else "grid"

    def set_library_view_mode(self, mode: str) -> None:
        self._qs.setValue("library/viewMode", mode)

    def library_thumbnail_size(self) -> int:
        return int(self._qs.value("library/thumbnailSize", self.library_default_thumbnail_size()))

    def set_library_thumbnail_size(self, size: int) -> None:
        self._qs.setValue("library/thumbnailSize", size)

    def library_preview_size(self) -> int:
        return int(self._qs.value("library/previewSize", LIBRARY_PREVIEW_DEFAULT))

    def set_library_preview_size(self, size: int) -> None:
        self._qs.setValue("library/previewSize", size)

    def library_sort(self) -> str:
        return str(self._qs.value("library/sort", self.library_default_sort()))

    def set_library_sort(self, sort_id: str) -> None:
        self._qs.setValue("library/sort", sort_id)

    # --- capture (Screen Capture PRD 8.1, 12.2) ---

    def capture_default_mode(self) -> str:
        return str(self._qs.value("capture/defaultMode", "region"))

    def set_capture_default_mode(self, mode: str) -> None:
        self._qs.setValue("capture/defaultMode", mode)

    def capture_hotkey(self, action: str) -> str:
        """Portable-text key sequence for ``capture.region`` / ``.window`` / ``.full_screen``."""
        key, default = CAPTURE_HOTKEY_KEYS[action]
        return str(self._qs.value(key, default))

    def set_capture_hotkey(self, action: str, key_sequence: str) -> None:
        key, _default = CAPTURE_HOTKEY_KEYS[action]
        self._qs.setValue(key, key_sequence)

    def capture_delay_seconds(self) -> int:
        return max(0, min(60, int(self._qs.value("capture/delaySeconds", 0))))

    def set_capture_delay_seconds(self, seconds: int) -> None:
        self._qs.setValue("capture/delaySeconds", max(0, min(60, seconds)))

    def capture_include_cursor(self) -> bool:
        return _as_bool(self._qs.value("capture/includeCursor", False))

    def set_capture_include_cursor(self, enabled: bool) -> None:
        self._qs.setValue("capture/includeCursor", enabled)

    def capture_play_sound(self) -> bool:
        return _as_bool(self._qs.value("capture/playSound", False))

    def set_capture_play_sound(self, enabled: bool) -> None:
        self._qs.setValue("capture/playSound", enabled)

    def capture_hide_window(self) -> bool:
        return _as_bool(self._qs.value("capture/hideWindow", True))

    def set_capture_hide_window(self, enabled: bool) -> None:
        self._qs.setValue("capture/hideWindow", enabled)

    def capture_copy_to_clipboard(self) -> bool:
        return _as_bool(self._qs.value("capture/copyToClipboard", False))

    def set_capture_copy_to_clipboard(self, enabled: bool) -> None:
        self._qs.setValue("capture/copyToClipboard", enabled)

    def capture_full_screen_scope(self) -> str:
        val = str(self._qs.value("capture/fullScreenScope", "monitor_under_cursor"))
        return "all_monitors" if val == "all_monitors" else "monitor_under_cursor"

    def set_capture_full_screen_scope(self, scope: str) -> None:
        self._qs.setValue("capture/fullScreenScope", scope)

    def capture_show_magnifier(self) -> bool:
        return _as_bool(self._qs.value("capture/showMagnifier", True))

    def set_capture_show_magnifier(self, enabled: bool) -> None:
        self._qs.setValue("capture/showMagnifier", enabled)

    def capture_tray_enabled(self) -> bool:
        return _as_bool(self._qs.value("capture/trayEnabled", True))

    def set_capture_tray_enabled(self, enabled: bool) -> None:
        self._qs.setValue("capture/trayEnabled", enabled)

    def capture_keep_running_in_tray(self) -> bool:
        return _as_bool(self._qs.value("capture/keepRunningInTray", False))

    def set_capture_keep_running_in_tray(self, enabled: bool) -> None:
        self._qs.setValue("capture/keepRunningInTray", enabled)

    def capture_onboarding_shown(self) -> bool:
        return _as_bool(self._qs.value("capture/onboardingShown", False))

    def set_capture_onboarding_shown(self, shown: bool) -> None:
        self._qs.setValue("capture/onboardingShown", shown)

    def capture_last_mode(self) -> str:
        return str(self._qs.value("capture/lastMode", self.capture_default_mode()))

    def set_capture_last_mode(self, mode: str) -> None:
        self._qs.setValue("capture/lastMode", mode)

    # --- session (open tabs) ---

    def session_open_files(self) -> list[str]:
        val = self._qs.value("session/openFiles", [])
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str) and val:
            return [val]
        return []

    def set_session_open_files(self, paths: list[str]) -> None:
        self._qs.setValue("session/openFiles", paths)

    def session_active_index(self) -> int:
        return int(self._qs.value("session/activeIndex", 0))

    def set_session_active_index(self, index: int) -> None:
        self._qs.setValue("session/activeIndex", index)


def _clamp(val: int, low: int, high: int) -> int:
    return max(low, min(high, val))


def _color_text(color: QColor | None) -> str:
    """``#AARRGGBB`` when the colour carries alpha, else ``#RRGGBB``."""
    if color is None:
        return ""
    if color.alpha() < 255:
        return color.name(QColor.NameFormat.HexArgb).upper()
    return color.name(QColor.NameFormat.HexRgb).upper()


def _color(val: object, default: str) -> QColor:
    color = QColor(str(val)) if isinstance(val, str) and val else QColor()
    return color if color.isValid() else QColor(default)


def _optional_color(val: object) -> QColor | None:
    if not isinstance(val, str) or not val:
        return None
    color = QColor(val)
    return color if color.isValid() else None


def _as_bool(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)
