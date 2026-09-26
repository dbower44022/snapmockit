"""Guides — user-placed horizontal and vertical reference lines (General UI PRD 6.5).

A guide is an orientation and a scene coordinate. The list lives on the
:class:`~snapmock.core.scene.SnapScene`; every change goes through a command in
``snapmock/commands/guide_commands.py``. :func:`snap_value` and
:func:`snap_rect_delta` are the snapping arithmetic that the view offers tools.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt


class GuideOrientation(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class GuideStyle(Enum):
    """A guide's line style (General UI PRD 2.66, Doug's decision A of 09-26-26)."""

    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"

    @property
    def pen_style(self) -> Qt.PenStyle:
        return _PEN_STYLES[self]


_PEN_STYLES = {
    GuideStyle.SOLID: Qt.PenStyle.SolidLine,
    GuideStyle.DASHED: Qt.PenStyle.DashLine,
    GuideStyle.DOTTED: Qt.PenStyle.DotLine,
}


@dataclass(frozen=True)
class Guide:
    """One guide: a horizontal line at ``y = position`` or a vertical one at ``x``.

    Since 2.66 a guide also carries its own colour (an ``#AARRGGBB`` string, or None for
    the Preferences colour at the Preferences opacity), its line style, and its lock. A
    locked guide is selected as any guide is and refuses the drag, the arrows, and
    Delete until it is unlocked in the Property Panel, the shape of the item lock.
    """

    orientation: GuideOrientation
    position: float
    color: str | None = None
    style: GuideStyle = GuideStyle.SOLID
    locked: bool = False

    def moved_to(self, position: float) -> Guide:
        return replace(self, position=position)

    def with_changes(self, **changes: Any) -> Guide:
        """A copy with *changes* applied (``color``, ``style``, ``locked``, ``position``)."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """The manifest entry; the 2.66 keys are written only when they differ from the
        defaults, so a project without them reads exactly as before."""
        data: dict[str, Any] = {"orientation": self.orientation.value, "position": self.position}
        if self.color is not None:
            data["color"] = self.color
        if self.style is not GuideStyle.SOLID:
            data["style"] = self.style.value
        if self.locked:
            data["locked"] = True
        return data

    @classmethod
    def from_dict(cls, data: object) -> Guide | None:
        """A guide from a manifest entry, or None when the entry is malformed. A missing
        or unreadable optional key reads as its default."""
        if not isinstance(data, dict):
            return None
        try:
            orientation = GuideOrientation(str(data.get("orientation")))
            position = float(data["position"])
        except (KeyError, TypeError, ValueError):
            return None
        color = data.get("color")
        color = color if isinstance(color, str) and color else None
        try:
            style = GuideStyle(str(data.get("style", "solid")))
        except ValueError:
            style = GuideStyle.SOLID
        return cls(orientation, position, color, style, bool(data.get("locked", False)))


def next_grid_line(value: float, grid: float, direction: float) -> float:
    """The grid line one step from *value* in *direction* (-1, 0, or +1 for none): the
    next line strictly beyond *value*, or the line a whole step away when *value* is on
    one already, so a Shift+Arrow nudge snaps first and steps after (General UI PRD
    Section 12 as Doug corrected it 09-16-26). Shared by the Select tool's nudge of items
    and the view's nudge of a selected guide."""
    if direction == 0:
        return value
    steps = value / grid
    nearest = round(steps)
    if abs(steps - nearest) < 1e-6:
        return (nearest + direction) * grid
    return (math.floor(steps) + 1) * grid if direction > 0 else math.floor(steps) * grid


def snap_value(value: float, targets: list[float], tolerance: float) -> float | None:
    """The target nearest *value* within *tolerance*, or None when none is close."""
    best: float | None = None
    best_distance = tolerance
    for target in targets:
        distance = abs(target - value)
        if distance <= best_distance:
            best, best_distance = target, distance
    return best


def snap_rect_delta(rect: QRectF, guides: list[Guide], tolerance: float) -> QPointF:
    """The offset that brings an edge or the centre of *rect* onto the nearest guide.

    Each axis is considered on its own: the left, centre, and right of the
    rectangle against the vertical guides, the top, middle, and bottom against
    the horizontal ones. The axis stays put when nothing is within *tolerance*.
    """
    vertical = [g.position for g in guides if g.orientation is GuideOrientation.VERTICAL]
    horizontal = [g.position for g in guides if g.orientation is GuideOrientation.HORIZONTAL]
    dx = _axis_delta((rect.left(), rect.center().x(), rect.right()), vertical, tolerance)
    dy = _axis_delta((rect.top(), rect.center().y(), rect.bottom()), horizontal, tolerance)
    return QPointF(dx, dy)


def _axis_delta(candidates: tuple[float, ...], targets: list[float], tolerance: float) -> float:
    best = 0.0
    best_distance = tolerance
    for candidate in candidates:
        target = snap_value(candidate, targets, best_distance)
        if target is not None and abs(target - candidate) <= best_distance:
            best, best_distance = target - candidate, abs(target - candidate)
    return best
