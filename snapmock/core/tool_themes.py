"""Tool presets and tool themes: the model, the value codec, the JSON stores, the session
state, and ``.smktheme`` read and write (General UI PRD 5.2, 11.8, 11.9, 15.4).

A **tool preset** is a named copy of one tool's creation defaults. A **tool theme** is a
named copy of every tool's creation defaults. Both are user data, not document state:
they live as JSON files under the application data directory and never touch the command
stack. The built-in Default theme is not a file: it is each tool's factory defaults with
the seven Preferences > Tools values laid over them (Phase 7 decision 7.2, option A).

The :class:`ToolThemeManager` owns the live state: which theme is active, which preset
each tool has applied, and whether a tool's current values still match either. Every
change it makes to a tool's defaults is announced through
``ToolManager.tool_defaults_changed`` so the Tool Options Bar, the Property Panel, and
the Tools menu label stay in step. The per-tool values and applied presets are written
to ``tool_state.json`` after every change and restored at startup, which is the
"last-used tool option values" of Section 15.4.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from snapmock import __version__
from snapmock.config.constants import (
    APP_NAME,
    ApplyTarget,
    ArcType,
    BadgeShape,
    BlurMode,
    BlurRegionShape,
    BorderStyle,
    BubbleShape,
    ColorFormat,
    CornerRadiusMode,
    DisplayMode,
    FontWeight,
    HeadSize,
    HeadStyle,
    LabelPosition,
    LineStyle,
    PolygonMode,
    StrokeCap,
    StrokeJoin,
    TailStyle,
    VerticalAlign,
)
from snapmock.config.migration import data_directory
from snapmock.core.emoji_data import SkinTone

if TYPE_CHECKING:
    from snapmock.config.settings import AppSettings
    from snapmock.tools.base_tool import BaseTool
    from snapmock.tools.tool_manager import ToolManager

ToolValues = dict[str, Any]
"""One tool's creation defaults, keyed as ``BaseTool.creation_defaults`` is."""

FORMAT_VERSION = 1
"""The version written into every preset, theme, and state file."""

THEME_FILE_KIND = "smktheme"
THEME_SUFFIX = ".smktheme"
DEFAULT_THEME_NAME = "Default"
CUSTOM_LABEL = "Custom"
COPY_SUFFIX = " Copy"

PRESETS_DIRNAME = "presets"
THEMES_DIRNAME = "themes"
STATE_FILENAME = "tool_state.json"

_ENUM_TYPES: dict[str, type[Enum]] = {
    "ApplyTarget": ApplyTarget,
    "ColorFormat": ColorFormat,
    "VerticalAlign": VerticalAlign,
    "BubbleShape": BubbleShape,
    "TailStyle": TailStyle,
    "BadgeShape": BadgeShape,
    "BorderStyle": BorderStyle,
    "DisplayMode": DisplayMode,
    "FontWeight": FontWeight,
    "LabelPosition": LabelPosition,
    "SkinTone": SkinTone,
    "StrokeCap": StrokeCap,
    "StrokeJoin": StrokeJoin,
    "HeadStyle": HeadStyle,
    "HeadSize": HeadSize,
    "LineStyle": LineStyle,
    "CornerRadiusMode": CornerRadiusMode,
    "ArcType": ArcType,
    "PolygonMode": PolygonMode,
    "BlurMode": BlurMode,
    "BlurRegionShape": BlurRegionShape,
}

OPACITY_KEYS: tuple[str, str] = ("fill_opacity", "stroke_opacity")
"""The two opacities that replaced ``opacity_pct`` for the vector tools (Vector Item
Properties decision 2, option A)."""


def migrate_opacity(values: ToolValues, defaults: ToolValues) -> ToolValues:
    """*values* with a stored ``opacity_pct`` read once into the opacity keys *defaults*
    has, when the tool no longer takes ``opacity_pct`` and neither new key is present.

    A preset, theme, or session state written before the Vector Item Properties work
    carried one opacity per shape tool; it becomes the same fraction for the fill and
    the stroke and the old key is dropped on the next write.
    """
    if "opacity_pct" not in values or "opacity_pct" in defaults:
        return values
    targets = [key for key in OPACITY_KEYS if key in defaults]
    if not targets or any(key in values for key in targets):
        return values
    out = dict(values)
    try:
        fraction = max(0.0, min(1.0, float(out.pop("opacity_pct")) / 100.0))
    except (TypeError, ValueError):
        return out
    for key in targets:
        out[key] = fraction
    return out


# The Preferences > Tools values and the creation-default key each one fills
# (General UI PRD 11.3; decision 7.2: these are the Default theme's values).
PREFERENCE_KEYS: tuple[str, ...] = (
    "stroke_color",
    "stroke_width",
    "fill_color",
    "font_family",
    "font_size",
    "smoothing",
    "start_number",
)


class ThemeFileError(ValueError):
    """A theme or preset file is not one this version can read."""


def application_data_directory() -> Path:
    """Where presets, themes, and the tool state live: ``~/.config/snapmockit`` on Linux.

    The platform's generic configuration location (``QStandardPaths``), under a
    lower-case folder named for the product, as the General UI PRD's example shows;
    ``config/migration.py`` answers with the earlier ``snapmock`` folder while only
    that one exists (packaging decision 4).
    """
    return data_directory()


# ---- the value codec ------------------------------------------------------------------


def encode_value(value: object) -> Any:
    """The JSON form of one creation-default value; ``TypeError`` for an unknown type."""
    if isinstance(value, QColor):
        return {"$color": value.name(QColor.NameFormat.HexArgb).upper()}
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Qt.AlignmentFlag):
        return {"$alignment": int(value.value)}
    if isinstance(value, Enum) and type(value).__name__ in _ENUM_TYPES:
        return {"$enum": type(value).__name__, "value": value.value}
    raise TypeError(f"cannot encode {type(value).__name__}")


def decode_value(raw: object) -> Any:
    """The value for one JSON form; ``ValueError`` when the form is not recognised."""
    if isinstance(raw, bool | int | float | str):
        return raw
    if isinstance(raw, dict):
        if "$color" in raw:
            color = QColor(str(raw["$color"]))
            if color.isValid():
                return color
            raise ValueError("bad colour")
        if "$alignment" in raw:
            return Qt.AlignmentFlag(int(raw["$alignment"]))
        if "$enum" in raw:
            cls = _ENUM_TYPES.get(str(raw["$enum"]))
            if cls is not None:
                return cls(raw.get("value"))
    raise ValueError("unknown value form")


def encode_values(values: ToolValues) -> dict[str, Any]:
    """Every encodable entry of *values*, in JSON form; the others are left out."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        try:
            out[key] = encode_value(value)
        except TypeError:
            continue
    return out


def decode_values(raw: object) -> ToolValues:
    """The creation defaults held in *raw*; malformed entries are skipped."""
    if not isinstance(raw, dict):
        return {}
    out: ToolValues = {}
    for key, value in raw.items():
        try:
            out[str(key)] = decode_value(value)
        except (ValueError, TypeError):
            continue
    return out


def values_equal(a: ToolValues, b: ToolValues) -> bool:
    """Whether two creation-default dictionaries hold the same values."""
    return encode_values(a) == encode_values(b)


# ---- the models -------------------------------------------------------------------------


@dataclass
class ToolPreset:
    """A named copy of one tool's creation defaults (General UI PRD 11.9)."""

    tool_id: str
    name: str
    values: ToolValues = field(default_factory=dict)


@dataclass
class ToolTheme:
    """A named copy of every tool's creation defaults (General UI PRD 11.8)."""

    name: str
    tools: dict[str, ToolValues] = field(default_factory=dict)
    builtin: bool = False


def unique_name(base: str, existing: set[str]) -> str:
    """*base* if unused, else the first ``base 2``, ``base 3``, … that is."""
    if base not in existing:
        return base
    n = 2
    while f"{base} {n}" in existing:
        n += 1
    return f"{base} {n}"


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.").lower()
    return slug or "item"


def _file_for(directory: Path, name: str, existing: dict[str, Path]) -> Path:
    """A file under *directory* for *name*: its slug, or a numbered slug on collision."""
    current = existing.get(name)
    if current is not None:
        return current
    taken = {p.name for p in existing.values()}
    candidate = f"{_slug(name)}.json"
    n = 2
    while candidate in taken:
        candidate = f"{_slug(name)}-{n}.json"
        n += 1
    return directory / candidate


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---- theme files (stored themes and .smktheme share one schema) ---------------------------


def theme_to_dict(theme: ToolTheme) -> dict[str, Any]:
    """The JSON document for *theme*: kind, format version, name, app version, tools."""
    return {
        "format": THEME_FILE_KIND,
        "format_version": FORMAT_VERSION,
        "name": theme.name,
        "app_version": __version__,
        "tools": {tid: encode_values(values) for tid, values in sorted(theme.tools.items())},
    }


def theme_from_dict(data: object) -> ToolTheme:
    """The theme held in a parsed theme document; ``ThemeFileError`` when it is not one."""
    if not isinstance(data, dict) or data.get("format") != THEME_FILE_KIND:
        raise ThemeFileError(f"not a {APP_NAME} tool theme file")
    version = data.get("format_version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise ThemeFileError(f"theme format version {version!r} is newer than this {APP_NAME}")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ThemeFileError("the theme has no name")
    tools_raw = data.get("tools")
    tools: dict[str, ToolValues] = {}
    if isinstance(tools_raw, dict):
        for tid, raw in tools_raw.items():
            tools[str(tid)] = decode_values(raw)
    return ToolTheme(name=name, tools=tools)


def read_theme_file(path: Path) -> ToolTheme:
    """Read a ``.smktheme`` (or stored theme) file; ``ThemeFileError`` when unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ThemeFileError(f"cannot read {path.name}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise ThemeFileError(f"{path.name} is not valid JSON") from exc
    return theme_from_dict(data)


def write_theme_file(theme: ToolTheme, path: Path) -> None:
    """Write *theme* as a ``.smktheme`` (or stored theme) file."""
    _write_json(path, theme_to_dict(theme))


# ---- the stores ---------------------------------------------------------------------------


class PresetStore:
    """The per-tool preset files under ``presets/<tool_id>/`` (General UI PRD 11.9)."""

    def __init__(self, root: Path) -> None:
        self._root = root / PRESETS_DIRNAME

    def _dir(self, tool_id: str) -> Path:
        return self._root / tool_id

    def _scan(self, tool_id: str) -> dict[str, tuple[Path, ToolPreset]]:
        found: dict[str, tuple[Path, ToolPreset]] = {}
        directory = self._dir(tool_id)
        if not directory.is_dir():
            return found
        for path in sorted(directory.glob("*.json")):
            data = _read_json(path)
            if data is None or data.get("tool_id") != tool_id:
                continue
            name = str(data.get("name") or "").strip()
            if not name or name in found:
                continue
            found[name] = (path, ToolPreset(tool_id, name, decode_values(data.get("values"))))
        return found

    def names(self, tool_id: str) -> list[str]:
        return [p.name for p in self.presets(tool_id)]

    def presets(self, tool_id: str) -> list[ToolPreset]:
        """The tool's presets, alphabetically."""
        found = self._scan(tool_id)
        return [found[name][1] for name in sorted(found, key=str.casefold)]

    def preset(self, tool_id: str, name: str) -> ToolPreset | None:
        entry = self._scan(tool_id).get(name)
        return entry[1] if entry is not None else None

    def save(self, preset: ToolPreset) -> None:
        """Create or overwrite the preset named ``preset.name``."""
        found = self._scan(preset.tool_id)
        path = _file_for(
            self._dir(preset.tool_id), preset.name, {n: e[0] for n, e in found.items()}
        )
        _write_json(
            path,
            {
                "format_version": FORMAT_VERSION,
                "tool_id": preset.tool_id,
                "name": preset.name,
                "values": encode_values(preset.values),
            },
        )

    def rename(self, tool_id: str, old: str, new: str) -> None:
        found = self._scan(tool_id)
        entry = found.get(old)
        if entry is None or old == new:
            return
        path, preset = entry
        preset.name = new
        path.unlink()
        self.save(preset)

    def delete(self, tool_id: str, name: str) -> None:
        entry = self._scan(tool_id).get(name)
        if entry is not None:
            entry[0].unlink(missing_ok=True)


class ThemeStore:
    """The user theme files under ``themes/`` (General UI PRD 11.8)."""

    def __init__(self, root: Path) -> None:
        self._dir = root / THEMES_DIRNAME

    def _scan(self) -> dict[str, tuple[Path, ToolTheme]]:
        found: dict[str, tuple[Path, ToolTheme]] = {}
        if not self._dir.is_dir():
            return found
        for path in sorted(self._dir.glob("*.json")):
            data = _read_json(path)
            if data is None:
                continue
            try:
                theme = theme_from_dict(data)
            except ThemeFileError:
                continue
            if theme.name == DEFAULT_THEME_NAME or theme.name in found:
                continue
            found[theme.name] = (path, theme)
        return found

    def themes(self) -> list[ToolTheme]:
        """The user themes, alphabetically."""
        found = self._scan()
        return [found[name][1] for name in sorted(found, key=str.casefold)]

    def names(self) -> list[str]:
        return [t.name for t in self.themes()]

    def theme(self, name: str) -> ToolTheme | None:
        entry = self._scan().get(name)
        return entry[1] if entry is not None else None

    def save(self, theme: ToolTheme) -> None:
        """Create or overwrite the theme named ``theme.name``."""
        found = self._scan()
        path = _file_for(self._dir, theme.name, {n: e[0] for n, e in found.items()})
        write_theme_file(theme, path)

    def rename(self, old: str, new: str) -> None:
        entry = self._scan().get(old)
        if entry is None or old == new:
            return
        path, theme = entry
        theme.name = new
        path.unlink()
        self.save(theme)

    def delete(self, name: str) -> None:
        entry = self._scan().get(name)
        if entry is not None:
            entry[0].unlink(missing_ok=True)


# ---- the live state -----------------------------------------------------------------------


class ToolThemeManager(QObject):
    """The active theme, each tool's applied preset, and the stores behind them.

    Signals
    -------
    active_theme_changed(str)
        The active theme's name, after Apply, a rename of the active theme, or a
        deletion that fell back to Default.
    presets_changed(str)
        A tool id whose preset list changed (save, update, rename, duplicate, delete).
    themes_changed()
        The theme list changed (new, duplicate, rename, delete, import).
    state_changed()
        A tool's applied preset or its "Custom" state may have changed; the dropdown
        label and the Tools menu's Active Theme label re-read.
    """

    active_theme_changed = pyqtSignal(str)
    presets_changed = pyqtSignal(str)
    themes_changed = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(
        self,
        tool_manager: ToolManager,
        settings: AppSettings,
        root: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._tools = tool_manager
        self._settings = settings
        self._root = root if root is not None else application_data_directory()
        self._presets = PresetStore(self._root)
        self._themes = ThemeStore(self._root)
        # Factory defaults: what each tool was constructed with, before any surface
        # wrote to it. Captured once, at construction, for the tools that have any.
        self._factory: dict[str, ToolValues] = {}
        for tool_id in tool_manager.tool_ids:
            tool = tool_manager.tool(tool_id)
            if tool is not None and tool.creation_defaults:
                self._factory[tool_id] = copy.deepcopy(tool.creation_defaults)
        self._applied: dict[str, str | None] = dict.fromkeys(self._factory)
        self._default_cache: ToolTheme = self._build_default()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(0)
        self._save_timer.timeout.connect(self.save_session)
        tool_manager.tool_defaults_changed.connect(self._on_tool_defaults_changed)

    # ---- properties ----

    @property
    def root(self) -> Path:
        return self._root

    @property
    def preset_store(self) -> PresetStore:
        return self._presets

    @property
    def theme_store(self) -> ThemeStore:
        return self._themes

    @property
    def tool_ids(self) -> list[str]:
        """The tools that have creation defaults, and so presets, in registration order."""
        return list(self._factory)

    def _tool(self, tool_id: str) -> BaseTool | None:
        return self._tools.tool(tool_id)

    def _values(self, tool_id: str) -> ToolValues:
        tool = self._tool(tool_id)
        return dict(tool.creation_defaults) if tool is not None else {}

    def current_values(self, tool_id: str) -> ToolValues:
        """A copy of the tool's creation defaults as they stand."""
        return copy.deepcopy(self._values(tool_id))

    def _migrated(self, tool_id: str, values: ToolValues) -> ToolValues:
        """*values* with a stored ``opacity_pct`` migrated for the tool (decision 2)."""
        return migrate_opacity(values, self._factory.get(tool_id, {}))

    def _preset_values(self, tool_id: str, preset: ToolPreset) -> ToolValues:
        """The values *preset* gives the tool: its own, migrated, over the active theme's
        for any key the tool gained after the preset was saved, so an older preset still
        applies whole and still reads as applied."""
        out = self.theme_values(tool_id)
        for key, value in self._migrated(tool_id, preset.values).items():
            if key in out:
                out[key] = copy.deepcopy(value)
        return out

    def _set_values(self, tool_id: str, values: ToolValues) -> bool:
        """Write *values* into the tool's defaults; True when anything changed."""
        tool = self._tool(tool_id)
        if tool is None:
            return False
        changed = False
        for key, value in self._migrated(tool_id, values).items():
            if key not in tool.creation_defaults:
                continue
            if values_equal({key: tool.creation_defaults[key]}, {key: value}):
                continue
            tool.creation_defaults[key] = copy.deepcopy(value)
            tool.on_option_changed(key, tool.creation_defaults[key])
            changed = True
        return changed

    def _announce(self, tool_id: str) -> None:
        self._tools.tool_defaults_changed.emit(tool_id)

    # ---- the Default theme (decision 7.2) ----

    def _preference_overlay(self, tool_id: str, values: ToolValues) -> ToolValues:
        """*values* with the seven Preferences > Tools values laid over them (PRD 11.3)."""
        s = self._settings
        out = copy.deepcopy(values)
        if "stroke_color" in out:
            out["stroke_color"] = QColor(s.default_stroke_color())
        if "stroke_width" in out:
            out["stroke_width"] = s.default_stroke_width()
        if "fill_color" in out:
            out["fill_color"] = QColor(s.default_fill_color())
        if "font_family" in out:
            out["font_family"] = s.default_font_family()
        if "font_size" in out:
            out["font_size"] = s.default_font_size()
        if "smoothing" in out:
            out["smoothing"] = s.freehand_smoothing()
        if "start_number" in out:
            out["start_number"] = s.numbered_step_start()
        return out

    def _build_default(self) -> ToolTheme:
        tools = {tid: self._preference_overlay(tid, v) for tid, v in self._factory.items()}
        return ToolTheme(DEFAULT_THEME_NAME, tools, builtin=True)

    def default_theme(self) -> ToolTheme:
        """The built-in Default theme: factory defaults under Preferences > Tools."""
        return copy.deepcopy(self._default_cache)

    def preferences_changed(self) -> None:
        """Preferences > Tools changed: rebuild Default and reach the un-overridden tools.

        Only while Default is the active theme, and only the tools whose values still
        matched the previous Default (a preset or a Custom edit is left alone).
        """
        previous = self._default_cache
        self._default_cache = self._build_default()
        if self.active_theme_name != DEFAULT_THEME_NAME:
            self.state_changed.emit()
            return
        for tool_id in self._factory:
            if self._applied.get(tool_id) is not None:
                continue
            if not values_equal(self._values(tool_id), previous.tools.get(tool_id, {})):
                continue
            if self._set_values(tool_id, self._default_cache.tools[tool_id]):
                self._announce(tool_id)
        self.state_changed.emit()

    # ---- themes ----

    def themes(self) -> list[ToolTheme]:
        """Default and the user themes, alphabetically by name."""
        items = [self.default_theme(), *self._themes.themes()]
        return sorted(items, key=lambda t: t.name.casefold())

    def theme_names(self) -> list[str]:
        return [t.name for t in self.themes()]

    def theme(self, name: str) -> ToolTheme | None:
        if name == DEFAULT_THEME_NAME:
            return self.default_theme()
        return self._themes.theme(name)

    @property
    def active_theme_name(self) -> str:
        name = self._settings.active_tool_theme()
        if name != DEFAULT_THEME_NAME and self._themes.theme(name) is None:
            return DEFAULT_THEME_NAME
        return name

    def active_theme(self) -> ToolTheme:
        theme = self.theme(self.active_theme_name)
        return theme if theme is not None else self.default_theme()

    def theme_values(self, tool_id: str, theme: ToolTheme | None = None) -> ToolValues:
        """The values *theme* (default: the active theme) gives *tool_id*.

        A theme that lacks the tool, or a key, falls back to the Default theme, so an
        imported theme from another version still sets every key.
        """
        if theme is None:
            theme = self.active_theme()
        base = copy.deepcopy(self._default_cache.tools.get(tool_id, {}))
        for key, value in self._migrated(tool_id, theme.tools.get(tool_id, {})).items():
            if key in base:
                base[key] = copy.deepcopy(value)
        return base

    def apply_theme(self, name: str) -> bool:
        """Make *name* the active theme: every tool reset, every override cleared."""
        theme = self.theme(name)
        if theme is None:
            return False
        self._settings.set_active_tool_theme(theme.name)
        for tool_id in self._factory:
            self._applied[tool_id] = None
            self._set_values(tool_id, self.theme_values(tool_id, theme))
            self._announce(tool_id)
        self.active_theme_changed.emit(theme.name)
        self.state_changed.emit()
        self.save_session()
        return True

    def capture_theme(self, name: str) -> ToolTheme:
        """New: the current settings of every tool saved as the theme *name*."""
        theme = ToolTheme(name, {tid: self.current_values(tid) for tid in self._factory})
        self._themes.save(theme)
        self.themes_changed.emit()
        return theme

    def duplicate_theme(self, name: str) -> ToolTheme | None:
        source = self.theme(name)
        if source is None:
            return None
        copy_name = unique_name(f"{source.name}{COPY_SUFFIX}", set(self.theme_names()))
        theme = ToolTheme(copy_name, copy.deepcopy(source.tools))
        self._themes.save(theme)
        self.themes_changed.emit()
        return theme

    def rename_theme(self, old: str, new: str) -> None:
        if old == DEFAULT_THEME_NAME or old == new:
            return
        self._themes.rename(old, new)
        if self._settings.active_tool_theme() == old:
            self._settings.set_active_tool_theme(new)
            self.active_theme_changed.emit(new)
        self.themes_changed.emit()

    def delete_theme(self, name: str) -> None:
        if name == DEFAULT_THEME_NAME:
            return
        self._themes.delete(name)
        if self._settings.active_tool_theme() == name:
            self._settings.set_active_tool_theme(DEFAULT_THEME_NAME)
            self.active_theme_changed.emit(DEFAULT_THEME_NAME)
            self.state_changed.emit()
        self.themes_changed.emit()

    def import_theme(self, path: Path) -> ToolTheme:
        """Import a ``.smktheme`` file as a user theme; ``ThemeFileError`` when unreadable."""
        theme = read_theme_file(path)
        theme.name = unique_name(theme.name, set(self.theme_names()))
        theme.builtin = False
        self._themes.save(theme)
        self.themes_changed.emit()
        return theme

    def export_theme(self, name: str, path: Path) -> bool:
        theme = self.theme(name)
        if theme is None:
            return False
        write_theme_file(ToolTheme(theme.name, theme.tools), path)
        return True

    # ---- presets ----

    def presets(self, tool_id: str) -> list[ToolPreset]:
        return self._presets.presets(tool_id)

    def preset_names(self, tool_id: str) -> list[str]:
        return self._presets.names(tool_id)

    def applied_preset(self, tool_id: str) -> str | None:
        """The name of the preset applied to *tool_id*, if one is."""
        return self._applied.get(tool_id)

    def apply_preset(self, tool_id: str, name: str) -> bool:
        preset = self._presets.preset(tool_id, name)
        if preset is None:
            return False
        self._applied[tool_id] = name
        self._set_values(tool_id, self._preset_values(tool_id, preset))
        self._announce(tool_id)
        self.state_changed.emit()
        self.save_session()
        return True

    def save_preset(self, tool_id: str, name: str) -> ToolPreset:
        """Save as Preset: the tool's current values under *name*, which becomes applied."""
        preset = ToolPreset(tool_id, name, self.current_values(tool_id))
        self._presets.save(preset)
        self._applied[tool_id] = name
        self.presets_changed.emit(tool_id)
        self.state_changed.emit()
        self.save_session()
        return preset

    def update_preset(self, tool_id: str) -> bool:
        """Update Preset: overwrite the applied preset with the tool's current values."""
        name = self._applied.get(tool_id)
        if name is None or self._presets.preset(tool_id, name) is None:
            return False
        self._presets.save(ToolPreset(tool_id, name, self.current_values(tool_id)))
        self.presets_changed.emit(tool_id)
        self.state_changed.emit()
        return True

    def rename_preset(self, tool_id: str, old: str, new: str) -> None:
        if old == new:
            return
        self._presets.rename(tool_id, old, new)
        if self._applied.get(tool_id) == old:
            self._applied[tool_id] = new
        self.presets_changed.emit(tool_id)
        self.state_changed.emit()
        self.save_session()

    def duplicate_preset(self, tool_id: str, name: str) -> ToolPreset | None:
        source = self._presets.preset(tool_id, name)
        if source is None:
            return None
        copy_name = unique_name(f"{name}{COPY_SUFFIX}", set(self.preset_names(tool_id)))
        preset = ToolPreset(tool_id, copy_name, copy.deepcopy(source.values))
        self._presets.save(preset)
        self.presets_changed.emit(tool_id)
        return preset

    def delete_preset(self, tool_id: str, name: str) -> None:
        self._presets.delete(tool_id, name)
        if self._applied.get(tool_id) == name:
            self._applied[tool_id] = None
        self.presets_changed.emit(tool_id)
        self.state_changed.emit()
        self.save_session()

    def reset_to_theme(self, tool_id: str) -> None:
        """Reset to Theme: the tool takes the active theme's values, its preset cleared."""
        self._applied[tool_id] = None
        self._set_values(tool_id, self.theme_values(tool_id))
        self._announce(tool_id)
        self.state_changed.emit()
        self.save_session()

    # ---- the labels ----

    def is_overridden(self, tool_id: str) -> bool:
        """Whether the tool differs from the active theme: a preset applied or a Custom edit."""
        if self._applied.get(tool_id) is not None:
            return True
        return not values_equal(self._values(tool_id), self.theme_values(tool_id))

    def is_modified(self) -> bool:
        """Whether any tool is overridden: the "(modified)" of the Active Theme label."""
        return any(self.is_overridden(tid) for tid in self._factory)

    def preset_is_modified(self, tool_id: str) -> bool:
        """Whether a preset is applied and the tool has moved off it (Update Preset shows)."""
        name = self._applied.get(tool_id)
        if name is None:
            return False
        preset = self._presets.preset(tool_id, name)
        if preset is None:
            return False
        return not values_equal(self._values(tool_id), self._preset_values(tool_id, preset))

    def current_label(self, tool_id: str) -> str:
        """The dropdown's text: the applied preset, the theme when unmodified, else Custom."""
        name = self._applied.get(tool_id)
        if name is not None:
            preset = self._presets.preset(tool_id, name)
            if preset is not None and values_equal(
                self._values(tool_id), self._preset_values(tool_id, preset)
            ):
                return name
            return CUSTOM_LABEL
        if values_equal(self._values(tool_id), self.theme_values(tool_id)):
            return self.active_theme_name
        return CUSTOM_LABEL

    # ---- session state (PRD 15.4) ----

    @property
    def state_path(self) -> Path:
        return self._root / STATE_FILENAME

    def _on_tool_defaults_changed(self, _tool_id: str) -> None:
        self.state_changed.emit()
        self._save_timer.start()

    def save_session(self) -> None:
        """Write every tool's values and applied preset to ``tool_state.json``."""
        self._save_timer.stop()
        tools: dict[str, Any] = {}
        for tool_id in self._factory:
            tools[tool_id] = {
                "preset": self._applied.get(tool_id),
                "values": encode_values(self._values(tool_id)),
            }
        try:
            _write_json(
                self.state_path,
                {
                    "format_version": FORMAT_VERSION,
                    "active_theme": self.active_theme_name,
                    "tools": tools,
                },
            )
        except OSError:
            pass

    def load_session(self) -> None:
        """Startup: the active theme into every tool, then the saved values over it."""
        theme = self.active_theme()
        for tool_id in self._factory:
            self._applied[tool_id] = None
            self._set_values(tool_id, self.theme_values(tool_id, theme))
        data = _read_json(self.state_path) if self.state_path.is_file() else None
        if data is not None and data.get("format_version") == FORMAT_VERSION:
            tools = data.get("tools")
            if isinstance(tools, dict):
                for tool_id, entry in tools.items():
                    if tool_id not in self._factory or not isinstance(entry, dict):
                        continue
                    self._set_values(tool_id, decode_values(entry.get("values")))
                    preset = entry.get("preset")
                    if isinstance(preset, str) and self._presets.preset(tool_id, preset):
                        self._applied[tool_id] = preset
        for tool_id in self._factory:
            self._announce(tool_id)
        self.state_changed.emit()
