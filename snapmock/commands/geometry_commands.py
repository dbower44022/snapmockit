"""Geometry commands — the point edits of Basic Shape PRD Sections 11.3 to 11.5.

``ModifyGeometryCommand`` records one geometry property of one item before and after a
point-editing drag and merges consecutive drags of the same point on the same item within
300 ms, so a drag made of several short strokes stays one undo step.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, cast

from PyQt6.QtCore import QLineF, QPointF

from snapmock.core.command_stack import BaseCommand
from snapmock.items.base_item import SnapGraphicsItem

_GEOMETRY_MERGE_ID = 3010
MERGE_WINDOW_MS = 300.0


def copy_geometry(value: Any) -> Any:
    """A copy of a geometry value that later edits of the original cannot reach."""
    if isinstance(value, QLineF):
        return QLineF(value)
    if isinstance(value, QPointF):
        return QPointF(value)
    if isinstance(value, list):
        return [copy_geometry(v) for v in value]
    if isinstance(value, tuple):
        return tuple(copy_geometry(v) for v in value)
    if isinstance(value, dict):
        return {k: copy_geometry(v) for k, v in value.items()}
    return value


def shape_name(item: SnapGraphicsItem) -> str:
    """The item's type as the Edit menu names it: "Line", "Arrow", "Polygon"."""
    return item.type_name.removesuffix("Item")


class ModifyGeometryCommand(BaseCommand):
    """Set one geometry property of *item* (``line``, ``control_point``, ``vertices``...).

    *point* names the dragged handle; only drags of the same point merge (11.3).
    """

    def __init__(
        self,
        item: SnapGraphicsItem,
        property_name: str,
        old_value: Any,
        new_value: Any,
        *,
        point: str = "",
        timestamp: float | None = None,
    ) -> None:
        self._item = item
        self._property = property_name
        self._old = copy_geometry(old_value)
        self._new = copy_geometry(new_value)
        self._point = point
        self._timestamp = time.monotonic() if timestamp is None else timestamp

    @property
    def item(self) -> SnapGraphicsItem:
        return self._item

    def redo(self) -> None:
        setattr(self._item, self._property, copy_geometry(self._new))

    def undo(self) -> None:
        setattr(self._item, self._property, copy_geometry(self._old))

    @property
    def description(self) -> str:
        return f"Edit {shape_name(self._item)} geometry"

    @property
    def merge_id(self) -> int:
        return _GEOMETRY_MERGE_ID

    def merge_with(self, other: BaseCommand) -> bool:
        if (
            not isinstance(other, ModifyGeometryCommand)
            or other._item is not self._item
            or other._property != self._property
            or other._point != self._point
            or (other._timestamp - self._timestamp) * 1000.0 > MERGE_WINDOW_MS
        ):
            return False
        self._new = copy_geometry(other._new)
        self._timestamp = other._timestamp
        return True


class ResizeShapeCommand(BaseCommand):
    """A handle resize of a shape: its position and its own measurements, before and after
    (Technical Architecture PRD 3.4.2). Stroke width and the other style values stay."""

    def __init__(
        self,
        item: SnapGraphicsItem,
        old_pos: QPointF,
        new_pos: QPointF,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> None:
        self._item = item
        self._old_pos = QPointF(old_pos)
        self._new_pos = QPointF(new_pos)
        self._old_state = old_state
        self._new_state = new_state

    @property
    def item(self) -> SnapGraphicsItem:
        return self._item

    def redo(self) -> None:
        self._item.restore_shape_state(self._new_state)
        self._item.setPos(self._new_pos)

    def undo(self) -> None:
        self._item.restore_shape_state(self._old_state)
        self._item.setPos(self._old_pos)

    @property
    def description(self) -> str:
        return f"Resize {shape_name(self._item)}"


class _VertexItem(Protocol):
    def insert_vertex(self, index: int, position: QPointF) -> None: ...
    def remove_vertex(self, index: int) -> QPointF: ...


class InsertVertexCommand(BaseCommand):
    """Insert a polygon vertex at *index* (Basic Shape PRD 11.4)."""

    def __init__(self, item: SnapGraphicsItem, index: int, position: QPointF) -> None:
        self._item = item
        self._index = index
        self._position = QPointF(position)

    def redo(self) -> None:
        cast(_VertexItem, self._item).insert_vertex(self._index, QPointF(self._position))

    def undo(self) -> None:
        cast(_VertexItem, self._item).remove_vertex(self._index)

    @property
    def description(self) -> str:
        return "Insert polygon vertex"


class RemoveVertexCommand(BaseCommand):
    """Remove the polygon vertex at *index* (Basic Shape PRD 11.5); the caller checks that
    more than three remain."""

    def __init__(self, item: SnapGraphicsItem, index: int, position: QPointF) -> None:
        self._item = item
        self._index = index
        self._position = QPointF(position)

    def redo(self) -> None:
        cast(_VertexItem, self._item).remove_vertex(self._index)

    def undo(self) -> None:
        cast(_VertexItem, self._item).insert_vertex(self._index, QPointF(self._position))

    @property
    def description(self) -> str:
        return "Remove polygon vertex"
