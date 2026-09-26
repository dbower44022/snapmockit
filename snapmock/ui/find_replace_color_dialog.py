"""FindReplaceColorDialog — find and replace a colour across all items (General UI PRD 3.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from snapmock.commands.macro_command import MacroCommand
from snapmock.commands.modify_property import ModifyPropertyCommand
from snapmock.core.command_stack import BaseCommand
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.ui.accessibility import apply_default_names
from snapmock.ui.color_picker import ColorPicker

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene

# Every colour-valued item property, in the order they are reported.
COLOR_PROPERTIES: tuple[str, ...] = (
    "stroke_color",
    "fill_color",
    "text_color",
    "bg_color",
    "border_color",
)


def color_matches(scene: SnapScene, color: QColor) -> list[tuple[SnapGraphicsItem, str]]:
    """Every ``(item, property)`` whose current colour equals *color* exactly, alpha included."""
    matches: list[tuple[SnapGraphicsItem, str]] = []
    # Every item, a group's members included: a colour inside a group is replaced too;
    # a locked item keeps its colours (the item lock, Doug's decision B of 09-25-26)
    for item in scene.all_annotation_items():
        if scene.is_locked(item):
            continue
        for prop in COLOR_PROPERTIES:
            if not hasattr(type(item), prop):
                continue
            value = getattr(item, prop)
            if isinstance(value, QColor) and value.rgba() == color.rgba():
                matches.append((item, prop))
    return matches


def replace_color_command(
    matches: list[tuple[SnapGraphicsItem, str]], find: QColor, replace: QColor
) -> MacroCommand:
    """One undoable command that sets every matched property to *replace*."""
    cmds: list[BaseCommand] = [
        ModifyPropertyCommand(item, prop, QColor(find), QColor(replace)) for item, prop in matches
    ]
    return MacroCommand(cmds, f"Replace colour {find.name()} with {replace.name()}")


class FindReplaceColorDialog(QDialog):
    """Edit > Find/Replace Color..."""

    def __init__(self, scene: SnapScene, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self.setWindowTitle("Find/Replace Color")

        form = QFormLayout(self)
        self._find_picker = ColorPicker(QColor("#FF0000"), allow_transparent=False)
        self._replace_picker = ColorPicker(QColor("#0000FF"))
        self._count_label = QLabel("")
        form.addRow("Find:", self._find_picker)
        form.addRow("Replace with:", self._replace_picker)
        form.addRow("Matches:", self._count_label)

        buttons = QDialogButtonBox()
        self._replace_button = QPushButton("Replace All")
        self._replace_button.clicked.connect(self.replace_all)
        buttons.addButton(self._replace_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._find_picker.color_changed.connect(lambda _c: self.refresh())
        self.refresh()
        apply_default_names(self)

    @property
    def find_color(self) -> QColor:
        return self._find_picker.color

    @find_color.setter
    def find_color(self, color: QColor) -> None:
        self._find_picker.color = color
        self.refresh()

    @property
    def replace_color(self) -> QColor:
        return self._replace_picker.color

    @replace_color.setter
    def replace_color(self, color: QColor) -> None:
        self._replace_picker.color = color

    @property
    def match_count(self) -> int:
        return len(self._matches)

    def refresh(self) -> None:
        self._matches = color_matches(self._scene, self.find_color)
        items = {id(item) for item, _prop in self._matches}
        n, m = len(self._matches), len(items)
        self._count_label.setText(
            f"{n} colour{'s' if n != 1 else ''} in {m} item{'s' if m != 1 else ''}"
        )

    def replace_all(self) -> None:
        if not self._matches:
            return
        cmd = replace_color_command(self._matches, self.find_color, self.replace_color)
        self._scene.command_stack.push(cmd)
        self.refresh()
