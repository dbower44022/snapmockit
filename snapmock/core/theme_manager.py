"""ThemeManager — light and dark themes, the System option, live switching, icons.

General UI PRD Section 13: the two themes live in ``resources/themes/light.qss``
and ``resources/themes/dark.qss``. Each file opens with named constants
(``@name: value;``) that the manager substitutes into the rules before the sheet
is applied, and that it reads for canvas rendering. Canvas code (selection
handles, grid, rulers, guides) reads :func:`current_theme` rather than the style
sheet. Icons (Section 13.4) are single SVG files recoloured for the theme at
load time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

log = logging.getLogger("snapmock.theme")

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
THEMES_DIR = RESOURCES_DIR / "themes"
ICONS_DIR = RESOURCES_DIR / "icons" / "tabler"

ICON_SIZES = (16, 24, 32)
ICON_SIZE_DEFAULT = 24
# Pixel sizes rendered into every QIcon so toolbars and menus find a sharp match
# at 100 and 200 percent display scaling.
_ICON_RENDER_SIZES = (16, 20, 24, 32, 48, 64)

UI_FONT_SIZES = ("small", "medium", "large")
UI_FONT_SIZE_DEFAULT = "medium"
_UI_FONT_DELTA = {"small": -1, "medium": 0, "large": 2}

_CONSTANT_RE = re.compile(r"^\s*@([A-Za-z0-9_-]+)\s*:\s*([^;]+);\s*$", re.MULTILINE)
_REFERENCE_RE = re.compile(r"@([A-Za-z0-9_-]+)")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class ThemeMode(Enum):
    """What the user chose: a theme, or the operating system's preference."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"

    @classmethod
    def from_value(cls, value: str) -> ThemeMode:
        try:
            return cls(value)
        except ValueError:
            return cls.LIGHT


@dataclass(frozen=True)
class ThemeColors:
    """Every colour a theme defines, as read from its style sheet constants.

    Field names are the ``@`` constant names with hyphens as underscores.
    """

    name: str
    window_bg: QColor
    panel_bg: QColor
    pasteboard: QColor
    text_primary: QColor
    text_secondary: QColor
    accent: QColor
    accent_text: QColor
    selection_handle: QColor
    selection_outline: QColor
    toolbar_bg: QColor
    toolbar_separator: QColor
    button_hover: QColor
    button_pressed: QColor
    error: QColor
    warning: QColor
    grid_lines: QColor
    grid_lines_major: QColor
    border: QColor
    input_bg: QColor
    ruler_bg: QColor
    ruler_text: QColor
    ruler_tick: QColor
    ruler_cursor: QColor
    canvas_border: QColor
    canvas_shadow: QColor
    empty_canvas_text: QColor
    checkerboard_a: QColor
    checkerboard_b: QColor
    guide: QColor
    crosshair: QColor
    overlay_dim: QColor
    tooltip_bg: QColor

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


COLOR_NAMES: tuple[str, ...] = tuple(f.name for f in fields(ThemeColors) if f.name != "name")


@dataclass(frozen=True)
class LoadedTheme:
    """A parsed theme file: its colours and the style sheet with constants resolved."""

    colors: ThemeColors
    style_sheet: str


def parse_theme_file(text: str, name: str) -> LoadedTheme:
    """Split *text* into constants and rules; resolve every ``@name`` in the rules.

    Raises ``ValueError`` when a constant the :class:`ThemeColors` dataclass
    needs is missing, or when a rule references a constant that is not defined.
    """
    constants: dict[str, str] = {}
    for match in _CONSTANT_RE.finditer(text):
        constants[match.group(1).replace("-", "_")] = match.group(2).strip()
    missing = [n for n in COLOR_NAMES if n not in constants]
    if missing:
        raise ValueError(f"theme {name!r} lacks constants: {', '.join(missing)}")
    rules = _COMMENT_RE.sub("", _CONSTANT_RE.sub("", text))

    def _resolve(match: re.Match[str]) -> str:
        key = match.group(1).replace("-", "_")
        if key not in constants:
            raise ValueError(f"theme {name!r} references undefined constant @{match.group(1)}")
        return constants[key]

    style_sheet = _REFERENCE_RE.sub(_resolve, rules)
    colors = ThemeColors(name=name, **{n: _parse_color(constants[n]) for n in COLOR_NAMES})
    return LoadedTheme(colors=colors, style_sheet=style_sheet)


def _parse_color(value: str) -> QColor:
    """``#RRGGBB`` or ``#AARRGGBB`` (Qt's ARGB order) to QColor."""
    color = QColor(value)
    if not color.isValid():
        raise ValueError(f"invalid theme colour {value!r}")
    return color


def load_theme(name: str) -> LoadedTheme:
    """Read and parse ``resources/themes/<name>.qss``."""
    path = THEMES_DIR / f"{name}.qss"
    return parse_theme_file(path.read_text(encoding="utf-8"), name)


def _fallback_theme() -> LoadedTheme:
    """The light theme with no rules, used only if the theme files cannot be read."""
    light = {
        "window_bg": "#F5F5F5",
        "panel_bg": "#FFFFFF",
        "pasteboard": "#E0E0E0",
        "text_primary": "#1A1A1A",
        "text_secondary": "#666666",
        "accent": "#2B579A",
        "accent_text": "#FFFFFF",
        "selection_handle": "#2B579A",
        "selection_outline": "#2B579A",
        "toolbar_bg": "#EEEEEE",
        "toolbar_separator": "#CCCCCC",
        "button_hover": "#D8D8D8",
        "button_pressed": "#C0C0C0",
        "error": "#D32F2F",
        "warning": "#F57C00",
        "grid_lines": "#33000000",
        "grid_lines_major": "#55000000",
        "border": "#CCCCCC",
        "input_bg": "#FFFFFF",
        "ruler_bg": "#EEEEEE",
        "ruler_text": "#333333",
        "ruler_tick": "#999999",
        "ruler_cursor": "#D32F2F",
        "canvas_border": "#B4B4B4",
        "canvas_shadow": "#66000000",
        "empty_canvas_text": "#999999",
        "checkerboard_a": "#FFFFFF",
        "checkerboard_b": "#CCCCCC",
        "guide": "#00BFFF",
        "crosshair": "#66000000",
        "overlay_dim": "#40000000",
        "tooltip_bg": "#FFFFE1",
    }
    colors = ThemeColors(name="light", **{k: QColor(v) for k, v in light.items()})
    return LoadedTheme(colors=colors, style_sheet="")


def system_prefers_dark() -> bool:
    """Whether the operating system reports a dark colour scheme (Section 13.1)."""
    app = QGuiApplication.instance()
    if app is None:
        return False
    hints = QGuiApplication.styleHints()
    if hints is None:
        return False
    return hints.colorScheme() == Qt.ColorScheme.Dark


class ThemeManager(QObject):
    """Owns the active theme, applies it to the application, and serves icons.

    One instance per process, reached through :func:`theme_manager`. The
    ``theme_changed`` signal carries the resolved theme name (``"light"`` or
    ``"dark"``) after the style sheet, palette, and font have been applied, so
    canvas code can repaint.
    """

    theme_changed = pyqtSignal(str)
    icon_size_changed = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode = ThemeMode.LIGHT
        self._loaded: dict[str, LoadedTheme] = {}
        self._current: LoadedTheme = self._load("light")
        self._icon_size = ICON_SIZE_DEFAULT
        self._ui_font_size = UI_FONT_SIZE_DEFAULT
        self._base_font_point_size: float | None = None
        self._icon_cache: dict[tuple[str, str], QIcon] = {}
        self._applied = False
        hints = QGuiApplication.styleHints() if QGuiApplication.instance() else None
        if hints is not None:
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    # --- state ---

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def resolved(self) -> str:
        """``"light"`` or ``"dark"``: the theme in effect after resolving System."""
        return self._current.colors.name

    @property
    def colors(self) -> ThemeColors:
        return self._current.colors

    @property
    def style_sheet(self) -> str:
        return self._current.style_sheet

    @property
    def icon_size(self) -> int:
        return self._icon_size

    @property
    def ui_font_size(self) -> str:
        return self._ui_font_size

    # --- switching ---

    def set_mode(self, mode: ThemeMode) -> None:
        """Choose Light, Dark, or System and apply the result live (Section 13.4)."""
        self._mode = mode
        self._apply_resolved()

    def set_icon_size(self, size: int) -> None:
        size = size if size in ICON_SIZES else ICON_SIZE_DEFAULT
        if size == self._icon_size:
            return
        self._icon_size = size
        self.icon_size_changed.emit(size)

    def set_ui_font_size(self, size: str) -> None:
        size = size if size in UI_FONT_SIZES else UI_FONT_SIZE_DEFAULT
        if size == self._ui_font_size:
            return
        self._ui_font_size = size
        self._apply_font()

    def apply(self) -> None:
        """Apply the resolved theme to the running QApplication."""
        self._applied = True
        self._apply_resolved(force=True)

    def _resolve_name(self) -> str:
        if self._mode is ThemeMode.SYSTEM:
            return "dark" if system_prefers_dark() else "light"
        return str(self._mode.value)

    def _apply_resolved(self, *, force: bool = False) -> None:
        name = self._resolve_name()
        if not force and name == self._current.colors.name:
            return
        self._current = self._load(name)
        self._icon_cache.clear()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setPalette(self._build_palette())
            # Setting the application style sheet makes Qt re-polish every live widget
            # in the process, which costs seconds once many exist; a second window, or a
            # re-apply of the same theme, leaves the sheet alone (found 09-14-26).
            if app.styleSheet() != self._current.style_sheet:
                app.setStyleSheet(self._current.style_sheet)
            self._apply_font()
        self.theme_changed.emit(name)

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode is ThemeMode.SYSTEM:
            self._apply_resolved()

    def _load(self, name: str) -> LoadedTheme:
        cached = self._loaded.get(name)
        if cached is not None:
            return cached
        try:
            theme = load_theme(name)
        except (OSError, ValueError) as exc:
            log.error("theme %r could not be loaded: %s", name, exc)
            theme = _fallback_theme()
        self._loaded[name] = theme
        return theme

    def _build_palette(self) -> QPalette:
        """A palette matching the theme, for the parts a style draws without QSS."""
        c = self._current.colors
        palette = QPalette()
        roles = QPalette.ColorRole
        palette.setColor(roles.Window, c.window_bg)
        palette.setColor(roles.WindowText, c.text_primary)
        palette.setColor(roles.Base, c.input_bg)
        palette.setColor(roles.AlternateBase, c.panel_bg)
        palette.setColor(roles.Text, c.text_primary)
        palette.setColor(roles.Button, c.toolbar_bg)
        palette.setColor(roles.ButtonText, c.text_primary)
        palette.setColor(roles.Highlight, c.accent)
        palette.setColor(roles.HighlightedText, c.accent_text)
        palette.setColor(roles.ToolTipBase, c.tooltip_bg)
        palette.setColor(roles.ToolTipText, c.text_primary)
        palette.setColor(roles.PlaceholderText, c.text_secondary)
        palette.setColor(roles.Link, c.accent)
        palette.setColor(roles.Mid, c.toolbar_separator)
        palette.setColor(roles.Dark, c.button_pressed)
        palette.setColor(roles.Light, c.panel_bg)
        palette.setColor(QPalette.ColorGroup.Disabled, roles.Text, c.text_secondary)
        palette.setColor(QPalette.ColorGroup.Disabled, roles.WindowText, c.text_secondary)
        palette.setColor(QPalette.ColorGroup.Disabled, roles.ButtonText, c.text_secondary)
        return palette

    def _apply_font(self) -> None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        if self._base_font_point_size is None:
            base = app.font().pointSizeF()
            self._base_font_point_size = base if base > 0 else 10.0
        font = QFont(app.font())
        font.setPointSizeF(self._base_font_point_size + _UI_FONT_DELTA[self._ui_font_size])
        app.setFont(font)

    # --- icons (Section 13.4) ---

    def icon(self, name: str) -> QIcon:
        """The Tabler icon *name* recoloured for the theme; a null icon if absent.

        The Normal state uses the primary text colour; the On state (a checked
        tool button) uses the accent colour.
        """
        key = (name, self._current.colors.name)
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached
        path = ICONS_DIR / f"{name}.svg"
        try:
            svg = path.read_text(encoding="utf-8")
        except OSError:
            log.warning("icon %r not found under %s", name, ICONS_DIR)
            icon = QIcon()
            self._icon_cache[key] = icon
            return icon
        c = self._current.colors
        icon = QIcon()
        for size in _ICON_RENDER_SIZES:
            icon.addPixmap(
                _render_svg(svg, c.text_primary, size), QIcon.Mode.Normal, QIcon.State.Off
            )
            icon.addPixmap(_render_svg(svg, c.accent, size), QIcon.Mode.Normal, QIcon.State.On)
            icon.addPixmap(
                _render_svg(svg, c.text_secondary, size), QIcon.Mode.Disabled, QIcon.State.Off
            )
        self._icon_cache[key] = icon
        return icon

    def icon_qsize(self) -> QSize:
        return QSize(self._icon_size, self._icon_size)


def _render_svg(svg: str, color: QColor, size: int) -> QPixmap:
    data = svg.replace("currentColor", color.name(QColor.NameFormat.HexRgb))
    renderer = QSvgRenderer(data.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pixmap


_instance: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """The process-wide ThemeManager, created on first use."""
    global _instance
    if _instance is None:
        _instance = ThemeManager()
    return _instance


def current_theme() -> ThemeColors:
    """The colours of the theme in effect; canvas code reads these at paint time."""
    return theme_manager().colors


def reset_theme_manager() -> None:
    """Drop the process-wide instance (tests)."""
    global _instance
    _instance = None
