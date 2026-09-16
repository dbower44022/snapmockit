"""GroupItem — a container item whose members are its child items (General UI PRD 3.6)."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsObject

from snapmock.items.base_item import (
    SnapGraphicsItem,
    transform_from_list,
    transform_to_list,
)

__all__ = ["GroupItem", "transform_from_list", "transform_to_list"]


class GroupItem(SnapGraphicsItem):
    """A group of annotation items that moves, resizes, and transforms as one unit.

    Group and Ungroup kickoff decision 1 (09-10-26), option A: the members are the
    group's Qt child items, so the group owns the layer membership, the z-value, the
    lock, and the transform, and every transform of the group carries its members.
    The group paints nothing of its own; its members paint. ``items.json`` nests the
    members' entries inside the group's entry under ``members``.
    """

    def __init__(
        self,
        members: list[SnapGraphicsItem] | None = None,
        parent: QGraphicsObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
        for member in members or []:
            self.add_member(member)

    # --- members ---

    @property
    def members(self) -> list[SnapGraphicsItem]:
        """The direct members in stacking order, bottom first."""
        children = [c for c in self.childItems() if isinstance(c, SnapGraphicsItem)]
        return sorted(children, key=lambda c: c.zValue())

    @property
    def member_count(self) -> int:
        return len(self.members)

    def descendants(self) -> list[SnapGraphicsItem]:
        """Every annotation item below this group, nested groups' members included."""
        found: list[SnapGraphicsItem] = []
        for member in self.members:
            found.append(member)
            if isinstance(member, GroupItem):
                found.extend(member.descendants())
        return found

    def add_member(self, item: SnapGraphicsItem) -> None:
        """Make *item* a child of this group, keeping its position relative to the group.

        The caller sets the member's position and transform; ``setParentItem`` does not
        preserve scene coordinates on its own.
        """
        self.prepareGeometryChange()
        item.setParentItem(self)
        item.layer_id = self._layer_id
        item.layer_opacity = self._layer_opacity
        item.layer_blend_mode = self._layer_blend_mode
        item.locked = self._locked

    def remove_member(self, item: SnapGraphicsItem) -> None:
        """Detach *item*; it stays in the scene as a top-level item when the group is in one."""
        if item.parentItem() is not self:
            return
        self.prepareGeometryChange()
        item.setParentItem(None)

    def refresh_geometry(self) -> None:
        """Tell the scene the bounding rect may have changed after a member edit."""
        self.prepareGeometryChange()
        self.update()

    # --- layer state and lock reach the members ---

    @property
    def layer_id(self) -> str:
        return self._layer_id

    @layer_id.setter
    def layer_id(self, value: str) -> None:
        SnapGraphicsItem.layer_id.fset(self, value)  # type: ignore[attr-defined]
        for member in self.members:
            member.layer_id = value

    @property
    def layer_opacity(self) -> float:
        return self._layer_opacity

    @layer_opacity.setter
    def layer_opacity(self, value: float) -> None:
        SnapGraphicsItem.layer_opacity.fset(self, value)  # type: ignore[attr-defined]
        for member in self.members:
            member.layer_opacity = value

    @property
    def layer_blend_mode(self) -> str:
        return self._layer_blend_mode

    @layer_blend_mode.setter
    def layer_blend_mode(self, value: str) -> None:
        SnapGraphicsItem.layer_blend_mode.fset(self, value)  # type: ignore[attr-defined]
        for member in self.members:
            member.layer_blend_mode = value

    @property
    def locked(self) -> bool:
        return self._locked

    @locked.setter
    def locked(self, value: bool) -> None:
        self._locked = value
        for member in self.members:
            member.locked = value

    # --- flips as a transform around the bounding-box centre ---
    # A group paints nothing, so the paint-time mirror of the base class never runs;
    # the mirror is folded into the item's transform instead, in the item's own
    # coordinates (before its rotation), which is where the base class applies it.

    @property
    def flip_horizontal(self) -> bool:
        return self._flip_horizontal

    @flip_horizontal.setter
    def flip_horizontal(self, value: bool) -> None:
        if value != self._flip_horizontal:
            self._flip_horizontal = value
            self._apply_mirror(-1.0, 1.0)

    @property
    def flip_vertical(self) -> bool:
        return self._flip_vertical

    @flip_vertical.setter
    def flip_vertical(self, value: bool) -> None:
        if value != self._flip_vertical:
            self._flip_vertical = value
            self._apply_mirror(1.0, -1.0)

    def _apply_mirror(self, sx: float, sy: float) -> None:
        centre = self.boundingRect().center()
        mirror = (
            QTransform()
            .translate(centre.x(), centre.y())
            .scale(sx, sy)
            .translate(-centre.x(), -centre.y())
        )
        rotation = QTransform().rotate(self.rotation())
        inverse, _ok = rotation.inverted()
        self.setTransform(inverse * mirror * rotation * self.transform())
        self.update()

    # --- QGraphicsItem overrides ---

    def boundingRect(self) -> QRectF:
        return self.childrenBoundingRect()

    def geometry_rect(self) -> QRectF:
        rect = QRectF()
        for member in self.members:
            rect = rect.united(member.mapRectToParent(member.geometry_rect()))
        return rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for member in self.members:
            path.addPath(member.mapToParent(member.shape()))
        return path

    def paint(self, painter: Any, option: Any, widget: Any = None) -> None:
        """A group paints nothing of its own; its members paint."""

    # --- geometry scaling (Property Panel width and height) ---

    def scale_geometry(self, sx: float, sy: float) -> None:
        self.prepareGeometryChange()
        for member in self.members:
            member.setPos(member.pos().x() * sx, member.pos().y() * sy)
            member.scale_geometry(sx, sy)

    # --- serialization ---

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "GroupItem",
            "item_id": self.item_id,
            "layer_id": self.layer_id,
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self.rotation(),
            "opacity": self.opacity(),
            "transform": transform_to_list(self.transform()),
            "flip_horizontal": self._flip_horizontal,
            "flip_vertical": self._flip_vertical,
            **self._blend_entry(),
            "members": [member.serialize() for member in self.members],
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> GroupItem:
        # The registry lives with the serializer, which imports this module.
        from snapmock.io.project_serializer import ITEM_REGISTRY

        group = cls()
        group.item_id = data.get("item_id", group.item_id)
        group._layer_id = data.get("layer_id", "")
        pos = data.get("pos", [0, 0])
        group.setPos(QPointF(pos[0], pos[1]))
        group.setRotation(data.get("rotation", 0.0))
        group.setOpacity(data.get("opacity", 1.0))
        group.setTransform(transform_from_list(data.get("transform")))
        # The mirror is already inside the stored transform; only the flags are restored.
        group._flip_horizontal = bool(data.get("flip_horizontal", False))
        group._flip_vertical = bool(data.get("flip_vertical", False))
        group._apply_blend_entry(data)
        entries = data.get("members", [])
        if isinstance(entries, list):
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                member_cls = ITEM_REGISTRY.get(str(entry.get("type", "")))
                if member_cls is None:
                    continue
                member = member_cls.deserialize(entry)
                member.setZValue(index)
                group.add_member(member)
        return group

    def renew_ids(self) -> None:
        """A new id for the group and for every item below it."""
        super().renew_ids()
        for item in self.descendants():
            item.renew_ids()

    def clone(self) -> GroupItem:
        """A deep copy with a new id for the group and for every item below it."""
        new_group = type(self).deserialize(self.serialize())
        new_group.renew_ids()
        return new_group

    # --- type label ---

    @property
    def type_name(self) -> str:
        return "Group"
