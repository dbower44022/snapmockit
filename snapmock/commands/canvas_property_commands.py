"""Canvas property commands — undoable canvas colour and DPI changes (General UI PRD 8.5)
and the canvas border (Navigation & Raster Operations PRD 12.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

from snapmock.config.constants import BorderStyle
from snapmock.core.command_stack import BaseCommand

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene

CANVAS_PROPERTIES = ("background_color", "canvas_dpi")
"""The scene properties this command may change."""


class SetCanvasPropertyCommand(BaseCommand):
    """Set the canvas background colour or the canvas DPI on a scene.

    The Property Panel's Canvas section pushes one per edit; consecutive
    edits of the same property merge into one undo entry.
    """

    def __init__(
        self, scene: SnapScene, prop_name: str, old_value: object, new_value: object
    ) -> None:
        if prop_name not in CANVAS_PROPERTIES:
            raise ValueError(f"unknown canvas property {prop_name!r}")
        self._scene = scene
        self._prop_name = prop_name
        self._old_value = old_value
        self._new_value = new_value

    def _apply(self, value: object) -> None:
        if self._prop_name == "background_color":
            assert isinstance(value, QColor)
            self._scene.set_background_color(value)
        else:
            assert isinstance(value, int)
            self._scene.set_canvas_dpi(value)

    def redo(self) -> None:
        self._apply(self._new_value)

    def undo(self) -> None:
        self._apply(self._old_value)

    @property
    def description(self) -> str:
        return (
            "Change canvas color" if self._prop_name == "background_color" else "Change canvas DPI"
        )

    @property
    def merge_id(self) -> int:
        return 3000 + CANVAS_PROPERTIES.index(self._prop_name)

    def merge_with(self, other: BaseCommand) -> bool:
        if isinstance(other, SetCanvasPropertyCommand) and other._prop_name == self._prop_name:
            self._new_value = other._new_value
            return True
        return False


BORDER_PROPERTIES = ("border_width", "border_color", "border_style", "border_shadow")
"""The four canvas border properties (Navigation PRD 10.3)."""

_BORDER_DESCRIPTIONS = {
    "border_width": "Change border width",
    "border_color": "Change border color",
    "border_style": "Change border style",
    "border_shadow": "Change border shadow",
}


class SetCanvasBorderCommand(BaseCommand):
    """Set one canvas border property on a scene (Navigation PRD 12.7).

    The Border tool's options bar and the Property Panel's Canvas section push one per
    edit; consecutive edits of the same property merge into one undo entry, as
    :class:`SetCanvasPropertyCommand` already does for the canvas colour and DPI.
    """

    def __init__(
        self, scene: SnapScene, prop_name: str, old_value: object, new_value: object
    ) -> None:
        if prop_name not in BORDER_PROPERTIES:
            raise ValueError(f"unknown border property {prop_name!r}")
        self._scene = scene
        self._prop_name = prop_name
        self._old_value = old_value
        self._new_value = new_value

    def _apply(self, value: object) -> None:
        if self._prop_name == "border_width":
            assert isinstance(value, int)
            self._scene.set_border_width(value)
        elif self._prop_name == "border_color":
            assert isinstance(value, QColor)
            self._scene.set_border_color(value)
        elif self._prop_name == "border_style":
            assert isinstance(value, BorderStyle)
            self._scene.set_border_style(value)
        else:
            assert isinstance(value, dict)
            self._scene.set_border_shadow(value)

    def redo(self) -> None:
        self._apply(self._new_value)

    def undo(self) -> None:
        self._apply(self._old_value)

    @property
    def description(self) -> str:
        return _BORDER_DESCRIPTIONS[self._prop_name]

    @property
    def merge_id(self) -> int:
        return 3100 + BORDER_PROPERTIES.index(self._prop_name)

    def merge_with(self, other: BaseCommand) -> bool:
        if isinstance(other, SetCanvasBorderCommand) and other._prop_name == self._prop_name:
            self._new_value = other._new_value
            return True
        return False
