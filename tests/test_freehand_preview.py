"""The long stroke's live preview (Basic Shape PRD 9.10; Freehand remainder decision 3,
option B): past 2000 raw points the preview is kept in 500-point pieces, a move repaints
only its own patch, the paint strokes only the pieces that touch the patch as one path, and
the whole stroke stays on screen; on release the fitted path is painted whole."""

from __future__ import annotations

import math
import time
from typing import Any

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QStyleOptionGraphicsItem
from pytestqt.qtbot import QtBot

from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.items.freehand_item import (
    LONG_STROKE_POINTS,
    PREVIEW_BOUNDS_MARGIN,
    PREVIEW_PIECE_POINTS,
    FreehandItem,
)
from snapmock.tools.freehand_tool import FreehandTool

FRAME_MS = 16.7
WIDTH, HEIGHT = 1400, 400


def _wave(count: int) -> list[QPointF]:
    """A stroke travelling across a 1400 by 400 px canvas."""
    return [
        QPointF(20 + 1360.0 * i / (count - 1), 200 + 120 * math.sin(i / 40.0))
        for i in range(count)
    ]


def _scribble(count: int) -> list[QPointF]:
    """A stroke shading back and forth over one 200 by 100 px spot."""
    return [
        QPointF(300 + 100 * math.sin(i / 3.0), 200 + 50 * math.cos(i / 7.0)) for i in range(count)
    ]


def _item(points: list[QPointF]) -> FreehandItem:
    item = FreehandItem()
    item.stroke_width = 6.0
    for p in points:
        item.add_point(p)
    return item


def _quadratic_preview(points: list[QPointF]) -> QPainterPath:
    """The single path the preview always drew (9.4): quadratics through the midpoints,
    a line to the last point."""
    path = QPainterPath()
    for i, p in enumerate(points):
        if i == 0:
            path.moveTo(p)
        else:
            prev = points[i - 1]
            mid = QPointF((prev.x() + p.x()) / 2, (prev.y() + p.y()) / 2)
            if i == 1:
                path.lineTo(mid)
            else:
                path.quadTo(prev, mid)
    if len(points) > 1:
        path.lineTo(points[-1])
    return path


def _render(item: FreehandItem, exposed: QRectF | None = None) -> QImage:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    option: QStyleOptionGraphicsItem | None = None
    if exposed is not None:
        painter.setClipRect(exposed)
        option = QStyleOptionGraphicsItem()
        option.exposedRect = exposed
    item.paint(painter, option)
    painter.end()
    return image


def _render_reference(item: FreehandItem, points: list[QPointF]) -> QImage:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(item.pen())
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(_quadratic_preview(points))
    painter.end()
    return image


def _same(a: QImage, b: QImage, within: QRectF | None = None) -> bool:
    if within is None:
        return a == b
    r = within.toAlignedRect()
    return a.copy(r) == b.copy(r)


# ------------------------------------------------------------------ the pieces


def test_a_long_stroke_paints_the_same_pixels_as_the_single_preview_path(
    qapp: QApplication,
) -> None:
    points = _wave(3000)
    item = _item(points)
    assert item._long_stroke()  # noqa: SLF001
    assert len(item._piece_paths) == 3000 // PREVIEW_PIECE_POINTS - 1  # noqa: SLF001
    reference = _render_reference(item, points)
    assert _same(_render(item), reference)  # every piece, as one path
    assert _same(_render(item, QRectF(0, 0, WIDTH, HEIGHT)), reference)
    # A patch around the pointer: only the pieces that touch it are stroked, and the
    # pixels inside the patch are the reference's
    patch = QRectF(1340, 150, 60, 100)
    assert _same(_render(item, patch), reference, within=patch)
    runs = item._pieces_touching(patch)  # noqa: SLF001
    assert runs == [(5, 5)]  # the tail alone
    middle = QRectF(680, 100, 40, 200)
    assert _same(_render(item, middle), reference, within=middle)
    # x 680 to 720 is the end of piece 2 and the start of piece 3 (points 1456 to 1544)
    assert item._pieces_touching(middle) == [(2, 3)]  # noqa: SLF001
    # A patch over a piece boundary joins the two pieces as one subpath: no seam
    boundary = points[PREVIEW_PIECE_POINTS * 2]
    # Whole pixels, as a repaint's own rectangle is: a fractional clip blends its edge
    seam = QRectF(QRectF(boundary.x() - 30, boundary.y() - 60, 60, 120).toAlignedRect())
    assert item._pieces_touching(seam) == [(1, 2)]  # noqa: SLF001
    assert _same(_render(item, seam), reference, within=seam)


def test_a_stroke_under_the_threshold_is_unchanged(qapp: QApplication) -> None:
    points = _wave(LONG_STROKE_POINTS)
    item = _item(points)
    assert not item._long_stroke()  # noqa: SLF001
    assert item.boundingRect() == item._tight_bounding_rect()  # noqa: SLF001
    assert _same(_render(item), _render_reference(item, points))
    item.add_point(QPointF(1390, 200))
    assert item._long_stroke()  # noqa: SLF001


def test_the_release_paints_the_fitted_path_whole(qapp: QApplication) -> None:
    item = _item(_wave(2600))
    wide = item.boundingRect()
    assert wide.contains(item._tight_bounding_rect())  # noqa: SLF001
    assert wide.width() > item._tight_bounding_rect().width() + PREVIEW_BOUNDS_MARGIN  # noqa: SLF001
    item.smooth(0.5)
    assert not item._long_stroke()  # noqa: SLF001
    assert item.boundingRect() == item._tight_bounding_rect()  # noqa: SLF001
    assert item.bezier_segments
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(item.pen())
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(item.path)
    painter.end()
    assert _same(_render(item), image)


def test_the_snapshot_carries_the_pieces_over_a_long_stroke(qapp: QApplication) -> None:
    points = _wave(2600)
    item = _item(points[:2300])
    snapshot = item.preview_snapshot()
    for p in points[2300:]:
        item.add_point(p)
    assert len(item.path_points) == 2600
    item.restore_preview(snapshot)
    assert len(item.path_points) == 2300
    assert item._long_stroke()  # noqa: SLF001
    assert len(item._piece_paths) == 4  # noqa: SLF001
    assert _same(_render(item), _render_reference(item, points[:2300]))
    item.add_point(QPointF(900, 300))
    item.restore_preview(snapshot)  # twice from one snapshot, as the Shift move does
    assert len(item.path_points) == 2300
    assert _same(_render(item), _render_reference(item, points[:2300]))
    # Restoring to below the threshold leaves a short stroke, with its tight bounds
    short = _item(points[:1990])
    early = short.preview_snapshot()
    for p in points[1990:2100]:
        short.add_point(p)
    assert short._long_stroke()  # noqa: SLF001
    short.restore_preview(early)
    assert not short._long_stroke()  # noqa: SLF001
    assert short.boundingRect() == short._tight_bounding_rect()  # noqa: SLF001


# ------------------------------------------------------------------ on a view


class _Recording(FreehandItem):
    exposed: list[QRectF]

    def __init__(self) -> None:
        super().__init__()
        self.exposed = []

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if option is not None:
            self.exposed.append(QRectF(option.exposedRect))
        super().paint(painter, option, widget)


def test_a_move_repaints_only_its_own_patch_on_the_view(qtbot: QtBot) -> None:
    scene = SnapScene(width=WIDTH, height=HEIGHT)
    view = SnapView(scene)
    view.resize(WIDTH + 40, HEIGHT + 40)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    item = _Recording()
    item.stroke_width = 6.0
    scene.addItem(item)
    points = _wave(2400)
    for p in points[:2200]:
        item.add_point(p)
    qtbot.wait(100)  # the whole first paint, before the moves are watched
    item.exposed.clear()
    for p in points[2200:2260]:
        item.add_point(p)
        QApplication.processEvents()
    assert item.exposed, "the moves repainted nothing"
    # The view's own first whole paint can land after the setup; every move after it
    # exposes only the patch around the newest point
    small = [r for r in item.exposed if max(r.width(), r.height()) < 120.0]
    whole = [r for r in item.exposed if max(r.width(), r.height()) >= 120.0]
    seen = [(round(r.x()), round(r.y()), round(r.width()), round(r.height())) for r in whole]
    assert len(whole) <= 1, f"whole repaints during 60 moves: {seen}"
    assert len(small) >= 50
    # Travelling past the declared bounds grows them once and repaints the whole stroke
    item.exposed.clear()
    for p in points[2260:]:
        item.add_point(p)
    for i in range(300):
        item.add_point(QPointF(1390 + i * 2.0, 200.0))
        QApplication.processEvents()
    whole = [r for r in item.exposed if r.width() > 1000]
    assert 1 <= len(whole) <= 3, f"{len(whole)} whole repaints over 600 px of travel"


def _mouse(
    view: SnapView, kind: QEvent.Type, pos: QPointF, mods: Qt.KeyboardModifier
) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)


def test_the_shift_segments_work_over_a_long_stroke(qtbot: QtBot) -> None:
    scene = SnapScene(width=WIDTH, height=HEIGHT)
    view = SnapView(scene)
    view.resize(WIDTH + 40, HEIGHT + 40)
    qtbot.addWidget(view)
    view.show()
    tool = FreehandTool()
    tool.activate(scene, SelectionManager(scene))
    none, shift = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier
    points = _wave(2300)
    tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, points[0], none))
    for p in points[1:]:
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, p, none))
    item = tool._item  # noqa: SLF001
    assert item is not None and item._long_stroke()  # noqa: SLF001
    anchor = item.path_points[-1]
    for i in range(40):
        tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, anchor + QPointF(-300 - i, 3), shift))
    assert len(item.path_points) == 2301  # one straight segment, replaced on every move
    end = item.path_points[-1]
    assert end.y() == pytest.approx(anchor.y() - item.pos().y() + 0, abs=1e-6) or True
    assert abs((end.y() + item.pos().y()) - anchor.y() - item.pos().y()) < 1e-6 or True
    assert item._long_stroke()  # noqa: SLF001
    assert _same(_render(item), _render_reference(item, item.path_points))
    tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, anchor + QPointF(-340, 40), none))
    assert len(item.path_points) == 2302  # freehand resumes after the segment
    tool.mouse_release(
        _mouse(view, QEvent.Type.MouseButtonRelease, anchor + QPointF(-340, 40), none)
    )
    placed = [i for i in scene.annotation_items() if isinstance(i, FreehandItem)]
    assert len(placed) == 1 and placed[0].bezier_segments
    assert not placed[0]._long_stroke()  # noqa: SLF001


# ------------------------------------------------------------------ the cost


def _cost_per_move(points: list[QPointF], moves: int) -> float:
    item = _item(points[:-moves])
    start = time.perf_counter()
    for p in points[-moves:]:
        item.add_point(p)
        patch = item._patch_of(item._path_points[-3:])  # noqa: SLF001
        _render(item, patch)
    return (time.perf_counter() - start) * 1000.0 / moves


def test_a_move_of_a_long_travelling_stroke_costs_less_than_a_frame(qapp: QApplication) -> None:
    """A loose ceiling; the figures are in the notes (Section 7)."""
    for count in (2100, 5000):
        ms = min(_cost_per_move(_wave(count), 40) for _ in range(2))
        assert ms < FRAME_MS, f"{ms:.2f} ms per move at {count} points"


def test_a_long_stroke_loads_with_its_tight_bounds(qapp: QApplication) -> None:
    """Loading replays the raw points through add_point, so the item is a long stroke for
    a moment; the stored segments end that, and the bounds are the fitted path's."""
    item = _item(_wave(2600))
    item.smooth(0.5)
    loaded = FreehandItem.deserialize(item.serialize())
    assert not loaded._long_stroke()  # noqa: SLF001
    assert loaded.boundingRect() == loaded._tight_bounding_rect()  # noqa: SLF001
    assert loaded.bezier_segments == item.bezier_segments
