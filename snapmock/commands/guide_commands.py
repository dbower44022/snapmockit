"""Guide commands — undoable add, move, remove, and clear of guides (General UI PRD 6.5)."""

from __future__ import annotations

from snapmock.core.command_stack import BaseCommand
from snapmock.core.guides import Guide
from snapmock.core.scene import SnapScene

_MOVE_GUIDE_MERGE_ID = 1005


class AddGuideCommand(BaseCommand):
    def __init__(self, scene: SnapScene, guide: Guide) -> None:
        self._scene = scene
        self._guide = guide

    def redo(self) -> None:
        self._scene.add_guide(self._guide)

    def undo(self) -> None:
        self._scene.remove_guide(self._guide)

    @property
    def description(self) -> str:
        return "Add Guide"


class RemoveGuideCommand(BaseCommand):
    def __init__(self, scene: SnapScene, guide: Guide) -> None:
        self._scene = scene
        self._guide = guide

    def redo(self) -> None:
        self._scene.remove_guide(self._guide)

    def undo(self) -> None:
        self._scene.add_guide(self._guide)

    @property
    def description(self) -> str:
        return "Remove Guide"


class MoveGuideCommand(BaseCommand):
    """Move one guide; consecutive moves of the same guide merge into one undo step."""

    def __init__(self, scene: SnapScene, guide: Guide, position: float) -> None:
        self._scene = scene
        self._old = guide
        self._new = guide.moved_to(position)

    def redo(self) -> None:
        self._scene.replace_guide(self._old, self._new)

    def undo(self) -> None:
        self._scene.replace_guide(self._new, self._old)

    @property
    def description(self) -> str:
        return "Move Guide"

    @property
    def merge_id(self) -> int:
        return _MOVE_GUIDE_MERGE_ID

    def merge_with(self, other: BaseCommand) -> bool:
        if isinstance(other, MoveGuideCommand) and other._old == self._new:
            self._new = other._new
            return True
        return False


class ChangeGuideCommand(BaseCommand):
    """Replace one guide with a changed copy: its colour, style, or lock (2.66)."""

    def __init__(self, scene: SnapScene, old: Guide, new: Guide, description: str) -> None:
        self._scene = scene
        self._old = old
        self._new = new
        self._description = description

    def redo(self) -> None:
        self._scene.replace_guide(self._old, self._new)

    def undo(self) -> None:
        self._scene.replace_guide(self._new, self._old)

    @property
    def description(self) -> str:
        return self._description


class ClearGuidesCommand(BaseCommand):
    def __init__(self, scene: SnapScene) -> None:
        self._scene = scene
        self._guides = list(scene.guides)

    def redo(self) -> None:
        self._scene.set_guides([])

    def undo(self) -> None:
        self._scene.set_guides(self._guides)

    @property
    def description(self) -> str:
        return "Clear All Guides"
