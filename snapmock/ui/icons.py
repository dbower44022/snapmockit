"""Icon names for tools, menu actions, and panel buttons, applied from the ThemeManager.

General UI PRD Section 13.4: the icon set is Tabler Icons (MIT), vendored under
``resources/icons/tabler/`` as one SVG per glyph and recoloured for the theme
by :meth:`ThemeManager.icon`. This module is the only place that knows which
glyph stands for which action, so a change of set is a change here and in the
resource directory.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar

from snapmock.config.constants import APP_NAME
from snapmock.config.shortcuts import SHORTCUTS
from snapmock.core.theme_manager import theme_manager

# Tool id -> Tabler icon name (Left Tool Palette, Tools menu, Section 3.7).
TOOL_ICONS: dict[str, str] = {
    "select": "pointer",
    "rectangle": "square",
    "ellipse": "circle",
    "arrow": "arrow-up-right",
    "line": "line",
    "arc": "vector-bezier-arc",
    "polygon": "polygon",
    "text": "typography",
    "freehand": "pencil",
    "blur": "blur",
    "highlight": "highlight",
    "callout": "message-2",
    "numbered_step": "circle-number-1",
    "stamp": "rubber-stamp",
    "emoji": "mood-smile",
    "crop": "crop",
    "raster_select": "marquee-2",
    "eyedropper": "color-picker",
    "pan": "hand-move",
    "zoom": "zoom-in",
    "lasso_select": "lasso",
}

# Menu action label (without the accelerator ampersand) -> Tabler icon name.
# Labels that repeat across menus (Flip Horizontal, Preferences...) share one glyph.
ACTION_ICONS: dict[str, str] = {
    # File
    "New": "file-plus",
    "Open...": "folder-open",
    "Open Recent": "history",
    "Clear Recent": "trash",
    "Close": "x",
    "Save": "device-floppy",
    "Save As...": "file-export",
    "Import Image...": "photo-plus",
    "Export...": "file-export",
    "Export Quick (PNG)": "download",
    "Print...": "printer",
    "Preferences...": "settings",
    "Quit": "power",
    # Edit
    "Undo": "arrow-back-up",
    "Redo": "arrow-forward-up",
    "Cut": "scissors",
    "Copy": "copy",
    "Paste": "clipboard",
    "Paste in Place": "clipboard-check",
    "Delete": "trash",
    "Duplicate": "copy-plus",
    "Select All": "select-all",
    "Select All Layers": "select-all",
    "Deselect": "deselect",
    "Select All Text": "text-recognition",
    "Find/Replace Color...": "color-swatch",
    # View
    "Zoom In": "zoom-in",
    "Zoom Out": "zoom-out",
    "Fit to Window": "zoom-scan",
    "Zoom to 100%": "zoom-reset",
    "Zoom to Selection": "zoom-in-area",
    "Show Grid": "grid-dots",
    "Snap to Grid": "magnet",
    "Show Rulers": "ruler",
    "Show Crosshairs": "crosshair",
    "Show Guides": "border-inner",
    "Snap to Guides": "magnet",
    "Lock Guides": "lock",
    "Clear All Guides": "trash",
    "Show Status Bar": "layout-bottombar",
    "Reset Layout": "layout-dashboard",
    "Dark Mode": "moon",
    "Next Tab": "chevron-right",
    "Previous Tab": "chevron-left",
    # Image
    "Crop to Canvas": "crop",
    "Resize Canvas...": "resize",
    "Resize Image...": "aspect-ratio",
    "Rotate Canvas 90° CW": "rotate-clockwise",
    "Rotate Canvas 90° CCW": "rotate",
    "Flip Canvas Horizontal": "flip-horizontal",
    "Flip Canvas Vertical": "flip-vertical",
    "Flip Horizontal": "flip-horizontal",
    "Flip Vertical": "flip-vertical",
    "Auto-Trim": "cut",
    # Layer
    "New Layer": "new-section",
    "Duplicate Layer": "copy",
    "Delete Layer": "trash",
    "Merge Down": "layers-intersect",
    "Merge Visible": "layers-union",
    "Flatten All": "layers-difference",
    "Rename Layer": "pencil",
    "Layer Properties...": "settings",
    "Move Up": "arrow-up",
    "Move Down": "arrow-down",
    "Move to Top": "arrow-bar-to-up",
    "Move to Bottom": "arrow-bar-to-down",
    # Arrange
    "Bring to Front": "arrow-bar-to-up",
    "Bring Forward": "arrow-up",
    "Send Backward": "arrow-down",
    "Send to Back": "arrow-bar-to-down",
    "Align Left": "layout-align-left",
    "Align Center": "layout-align-center",
    "Align Center (H)": "layout-align-center",
    "Align Right": "layout-align-right",
    "Align Top": "layout-align-top",
    "Align Middle": "layout-align-middle",
    "Align Middle (V)": "layout-align-middle",
    "Align Bottom": "layout-align-bottom",
    "Distribute Horizontally": "layout-distribute-horizontal",
    "Distribute Vertically": "layout-distribute-vertical",
    "Align to Canvas Center": "focus-centered",
    "Group": "components",
    "Ungroup": "components-off",
    # Tools
    "Tool Themes...": "palette",
    # Library
    "Open Library...": "folder",
    "Move Library...": "folder-symlink",
    "New Folder": "folder-plus",
    "New Canvas": "file-plus",
    "Reveal in File Manager": "external-link",
    "Library Preferences...": "settings",
    # Capture
    "Capture Region": "screenshot",
    "Capture Active Window": "app-window",
    "Capture Full Screen": "device-desktop",
    "Capture Preferences...": "settings",
    f"Show {APP_NAME}": "eye",
    f"Quit {APP_NAME}": "power",
    # Help
    "Welcome / Getting Started": "home",
    "Documentation": "book",
    "Keyboard Shortcuts": "keyboard",
    "Report a Bug": "bug",
    "Check for Updates": "refresh",
    f"About {APP_NAME}": "info-circle",
}

# Buttons outside menus: the capture control and the panel action bars.
CAPTURE_ICON = "camera"
ADD_ICON = "plus"
REMOVE_ICON = "minus"


def plain_label(text: str) -> str:
    """A menu label without its accelerator ampersand."""
    return text.replace("&&", "\x00").replace("&", "").replace("\x00", "&")


def tool_tooltip(tool_id: str, display_name: str) -> str:
    """``"Name (Shortcut)"`` for a tool button (PRD 4.3), or the name alone."""
    key = SHORTCUTS.get(f"tool.{tool_id}", "")
    if not key:
        return display_name
    native = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
    return f"{display_name} ({native})"


def apply_action_icons(actions: Iterable[QAction]) -> None:
    """Set the icon of every action whose label is in :data:`ACTION_ICONS`, recursively."""
    manager = theme_manager()
    for action in actions:
        if action.isSeparator():
            continue
        label = plain_label(action.text())
        name = ACTION_ICONS.get(label)
        if name is not None:
            action.setIcon(manager.icon(name))
        submenu = action.menu()
        if isinstance(submenu, QMenu):
            apply_action_icons(submenu.actions())


def apply_tool_action_icons(actions: dict[str, QAction]) -> None:
    """Icons for the Tools menu rows, keyed by tool id."""
    manager = theme_manager()
    for tool_id, action in actions.items():
        name = TOOL_ICONS.get(tool_id)
        if name is not None:
            action.setIcon(manager.icon(name))


def apply_menu_bar_icons(menu_bar: QMenuBar | None) -> None:
    if menu_bar is not None:
        apply_action_icons(menu_bar.actions())
