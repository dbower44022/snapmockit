"""Tool Themes dialog: select, create, edit, import, export, and apply tool themes
(General UI PRD 11.8).

Opened from Tools > Tool Themes... The theme list on the left marks the active theme
with a check; the preview on the right summarises the selected theme by tool. New saves
the current tool settings under a name; Duplicate copies with the " Copy" suffix; Rename
edits the name in place; Delete confirms; Import reads and Export writes a ``.smktheme``
file. Apply makes the selected theme active, resetting every tool and clearing the
per-tool preset overrides; Cancel closes without change.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.constants import APP_NAME
from snapmock.core.tool_themes import (
    DEFAULT_THEME_NAME,
    THEME_SUFFIX,
    ThemeFileError,
    ToolTheme,
    ToolThemeManager,
)
from snapmock.ui.manage_presets_dialog import summarise_values
from snapmock.ui.unmet_requirements import check_requirements

if TYPE_CHECKING:
    from snapmock.tools.tool_manager import ToolManager

ACTIVE_MARK = "✓ "
THEME_FILE_FILTER = f"{APP_NAME} Tool Theme (*{THEME_SUFFIX})"


class ToolThemesDialog(QDialog):
    """Manage the system-wide tool themes and apply one (PRD 11.8)."""

    def __init__(
        self,
        themes: ToolThemeManager,
        tool_manager: ToolManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._themes = themes
        self._tools = tool_manager
        self._updating = False
        self.setWindowTitle("Tool Themes")
        self.setObjectName("ToolThemesDialog")
        self.setMinimumSize(720, 440)

        outer = QVBoxLayout(self)
        panels = QHBoxLayout()
        outer.addLayout(panels, 1)

        left = QVBoxLayout()
        self._list = QListWidget()
        self._list.setObjectName("ThemeList")
        self._list.setAccessibleName("Tool themes")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._list.itemChanged.connect(self._on_item_changed)
        left.addWidget(self._list, 1)

        actions = QHBoxLayout()
        self._buttons: dict[str, QPushButton] = {}
        for label, slot in (
            ("New", self._new),
            ("Duplicate", self._duplicate),
            ("Rename", self._rename),
            ("Delete", self._delete),
            ("Import", self._import),
            ("Export", self._export),
        ):
            button = QPushButton(label)
            button.setAccessibleName(f"{label} theme")
            button.clicked.connect(slot)
            actions.addWidget(button)
            self._buttons[label] = button
        left.addLayout(actions)
        panels.addLayout(left, 2)

        self._preview = QLabel()
        self._preview.setObjectName("ThemePreview")
        self._preview.setAccessibleName("Theme preview")
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setWordWrap(True)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._preview)
        panels.addWidget(scroll, 3)

        buttons = QDialogButtonBox()
        apply_button = buttons.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        if apply_button is not None:
            apply_button.setAccessibleName("Apply theme")
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        themes.themes_changed.connect(self._reload)
        themes.active_theme_changed.connect(self._on_active_theme_changed)
        self._reload()
        self.select(themes.active_theme_name)

    # ---- the list ----

    def theme_names(self) -> list[str]:
        """The names shown, top to bottom, without the active mark."""
        names = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None:
                names.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return names

    def display_texts(self) -> list[str]:
        return [
            self._list.item(row).text()  # type: ignore[union-attr]
            for row in range(self._list.count())
        ]

    def selected_name(self) -> str | None:
        item = self._list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def preview_text(self) -> str:
        return self._preview.text()

    def select(self, name: str) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == name:
                self._list.setCurrentItem(item)
                return

    def _display(self, name: str) -> str:
        return f"{ACTIVE_MARK}{name}" if name == self._themes.active_theme_name else name

    def _reload(self) -> None:
        selected = self.selected_name()
        self._updating = True
        try:
            self._list.clear()
            for theme in self._themes.themes():
                item = QListWidgetItem(self._display(theme.name))
                item.setData(Qt.ItemDataRole.UserRole, theme.name)
                if not theme.builtin:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setToolTip("Built-in; cannot be renamed or deleted" if theme.builtin else "")
                self._list.addItem(item)
        finally:
            self._updating = False
        if selected is not None:
            self.select(selected)
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)
        self._refresh_preview()

    def _on_active_theme_changed(self, _name: str) -> None:
        self._reload()

    def _on_current_changed(
        self, _current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if not self._updating:
            self._refresh_preview()

    # ---- the preview (PRD 11.8) ----

    def _refresh_preview(self) -> None:
        name = self.selected_name()
        theme = self._themes.theme(name) if name is not None else None
        if theme is None:
            self._preview.setText("")
            return
        self._preview.setText(self._preview_html(theme))

    def _preview_html(self, theme: ToolTheme) -> str:
        """Every tool with presets, in registration order: its name and a value summary."""
        parts = [f"<h3>{escape(theme.name)}</h3>"]
        for tool_id in self._themes.tool_ids:
            tool = self._tools.tool(tool_id)
            if tool is None:
                continue
            values = self._themes.theme_values(tool_id, theme)
            summary = summarise_values(values, tool.options_controls)
            parts.append(f"<p><b>{escape(tool.display_name)}</b><br>{summary}</p>")
        return "".join(parts)

    # ---- prompts, kept as methods so tests can stand in for them ----

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        text, ok = QInputDialog.getText(self, title, "Theme name:", text=initial)
        return text.strip() if ok else None

    def _confirm_delete(self, name: str) -> bool:
        answer = QMessageBox.question(
            self, "Delete Theme", f'Delete the theme "{name}"? This cannot be undone.'
        )
        return answer == QMessageBox.StandardButton.Yes

    def _ask_import_path(self) -> Path | None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Import Theme", "", THEME_FILE_FILTER)
        return Path(path_str) if path_str else None

    def _ask_export_path(self, name: str) -> Path | None:
        suggested = f"{name}{THEME_SUFFIX}"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Theme", suggested, THEME_FILE_FILTER
        )
        if not path_str:
            return None
        path = Path(path_str)
        return path if path.suffix == THEME_SUFFIX else path.with_suffix(THEME_SUFFIX)

    def _show_error(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    # ---- the actions ----

    def _require_selection(self, action: str) -> str | None:
        name = self.selected_name()
        if check_requirements(self, action, [(name is not None, "a theme selected")]):
            return name
        return None

    def _require_user_theme(self, action: str) -> str | None:
        name = self.selected_name()
        if check_requirements(
            self,
            action,
            [
                (name is not None, "a theme selected"),
                (name != DEFAULT_THEME_NAME, "a theme other than the built-in Default"),
            ],
        ):
            return name
        return None

    def _valid_new_name(self, action: str, name: str | None) -> str | None:
        if name is None:
            return None
        taken = name in self._themes.theme_names()
        if check_requirements(
            self,
            action,
            [(bool(name), "a name"), (not taken, f'a name not already used ("{name}" is)')],
        ):
            return name
        return None

    def _new(self) -> None:
        """New: the current tool settings saved as a theme, after a name (PRD 11.8)."""
        name = self._valid_new_name("New", self._ask_name("New Theme"))
        if name is None:
            return
        theme = self._themes.capture_theme(name)
        self.select(theme.name)

    def _duplicate(self) -> None:
        name = self._require_selection("Duplicate")
        if name is None:
            return
        copy = self._themes.duplicate_theme(name)
        if copy is not None:
            self.select(copy.name)

    def _rename(self) -> None:
        """Rename: edit the selected user theme's name in place."""
        if self._require_user_theme("Rename") is None:
            return
        item = self._list.currentItem()
        if item is None:
            return
        self._updating = True
        try:
            item.setText(str(item.data(Qt.ItemDataRole.UserRole)))
        finally:
            self._updating = False
        self._list.editItem(item)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        old = str(item.data(Qt.ItemDataRole.UserRole))
        new = item.text().strip().removeprefix(ACTIVE_MARK.strip()).strip()
        if new == old:
            self._reload()
            return
        if self._valid_new_name("Rename", new) is None:
            self._reload()
            return
        self._themes.rename_theme(old, new)
        self.select(new)

    def _delete(self) -> None:
        name = self._require_user_theme("Delete")
        if name is None:
            return
        if not check_requirements(
            self,
            "Delete",
            [(name != self._themes.active_theme_name, "a theme that is not the active theme")],
        ):
            return
        if self._confirm_delete(name):
            self._themes.delete_theme(name)

    def _import(self) -> None:
        path = self._ask_import_path()
        if path is None:
            return
        try:
            theme = self._themes.import_theme(path)
        except ThemeFileError as exc:
            self._show_error("Import Theme", f"Cannot import {path.name}: {exc}.")
            return
        self.select(theme.name)

    def _export(self) -> None:
        name = self._require_selection("Export")
        if name is None:
            return
        path = self._ask_export_path(name)
        if path is None:
            return
        try:
            self._themes.export_theme(name, path)
        except OSError as exc:
            self._show_error("Export Theme", f"Cannot write {path.name}: {exc.strerror or exc}.")

    def _apply(self) -> None:
        """Apply: the selected theme becomes active; every tool reset, overrides cleared."""
        name = self._require_selection("Apply")
        if name is None:
            return
        self._themes.apply_theme(name)
        self.accept()
