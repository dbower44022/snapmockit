"""FreehandItem — freehand drawn path annotation.

Basic Shape PRD Section 9 and 10.7 (Basic Shape remainder decision 2, option A): the item
keeps the raw sampled points (``path_points``) and the smoothed path as cubic Bezier
segments (``bezier_segments``), with the ``smoothing`` value that produced them,
``is_closed``, and ``pressure_data`` (reserved, always null). While a stroke is drawn it
paints the raw points joined by quadratic curves (9.4); on release the two-stage pipeline
of 9.3 runs (Ramer-Douglas-Peucker simplification, then least-squares cubic fitting) and
the segments are painted from then on. Re-smoothing starts again from the raw points, so it
never loses the stroke; a hand edit of the segments is replaced by a re-smooth.

A long stroke (9.10; Freehand remainder decision 3, option B): past 2000 raw points the
preview is kept in pieces of 500 points, each added point repaints only the patch it
changed, and the paint strokes only the pieces that touch the patch, joined as one path,
so the cost of a move is bounded by the pieces near the pointer and the whole stroke stays
on screen. On release the fitted path is painted whole, as for any stroke.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPainterPathStroker
from PyQt6.QtWidgets import QGraphicsItem

from snapmock.core.path_utils import (
    BezierSegment,
    fit_cubic_beziers,
    point_tangents,
    simplify_rdp_indices,
    stroke_noise,
    travel_average,
)
from snapmock.items.vector_item import VectorItem, _clamp_unit

SMOOTHING_REACH_PX = 30.0
"""The averaging stage's reach at 100 percent smoothing: each raw point is replaced by the
mean of the points within smoothing times 30 px of travel either side, before the two
stages of 9.3 run. Decision 4 of the Freehand remainder work (09-13-26): 9.3's two stages
alone could not remove a hand tremor without either bowing between sparse points or
distorting small shapes, and a moving average is what the Highlighter's PRD already uses
(notes Section 8.9)."""

SIMPLIFY_TOLERANCE_PX = 0.5
"""Stage 1's tolerance at every smoothing: points within half a pixel of the simplified
line are dropped. 9.3 scaled this with the slider, to 5 px at 100 percent; decision 4
fixes it, because a fit that sees only widely spaced points bows between them, so the
curve is pinned to the averaged stroke within the fitting error everywhere along it."""

SMOOTHING_ERROR_PX = 10.0
"""Stage 2's fitting error at 100 percent smoothing: smoothing times 10 px, the curve's
largest deviation from the averaged stroke. 9.3 wrote 3 px (decision 4)."""

MIN_FIT_ERROR_PX = 0.5
"""The fitting error at 0 percent, so the curve follows the points without a segment for
every pixel of the stroke."""

NOISE_FLOOR_FACTOR = 3.0
"""The fitting error is never below this many times the stroke's own noise
(:func:`stroke_noise`), at every smoothing, so the fit never chases the whole-pixel
rounding of mouse coordinates or a shaky hand with a segment per point: on such a stroke
the two-stage pipeline took over a second at 5000 points against 9.10's 50 ms (Freehand
remainder decision 2, option B). A smooth stroke's noise is near zero, so its fit is the
one it always was."""

NOISE_FLOOR_MAX_PX = 1.5
"""The noise floor never rises past 1.5 px, three times the noise of whole-pixel mouse
coordinates: the fitting error of 15 percent smoothing, so the slider keeps its meaning
from there up on the noisiest stroke."""

DEFAULT_SMOOTHING = 0.5

HIT_MIN_WIDTH = 8.0
"""The narrowest hit band (9.9): a thin stroke is still easy to click."""

LONG_STROKE_POINTS = 2000
"""9.10: a stroke over this many raw points is a long stroke while it is drawn, and the
item paints only the pieces of its preview that a repaint touches (Freehand remainder
decision 3, option B)."""

PREVIEW_PIECE_POINTS = 500
"""9.10's 500 points: the size of each piece of a long stroke's preview, which is the most
one move has to stroke while the stroke travels."""

PREVIEW_BOUNDS_MARGIN = 256.0
"""How far past the stroke a long stroke's bounding rectangle reaches, so the rectangle
grows, and the whole stroke is repainted, once every 256 px of travel and not on every
move."""

PreviewSnapshot = tuple[list[QPointF], QPainterPath, tuple[Any, ...]]
"""What :meth:`FreehandItem.preview_snapshot` returns: the raw points, the preview path,
and the long stroke's bookkeeping, restored together by :meth:`FreehandItem.restore_preview`."""


def _point(raw: object) -> QPointF | None:
    if isinstance(raw, dict) and "x" in raw and "y" in raw:
        return QPointF(float(raw["x"]), float(raw["y"]))
    if isinstance(raw, list | tuple) and len(raw) == 2:
        return QPointF(float(raw[0]), float(raw[1]))
    return None


def _point_data(p: QPointF) -> dict[str, float]:
    return {"x": p.x(), "y": p.y()}


def _copy_segments(segments: list[BezierSegment]) -> list[BezierSegment]:
    return [(QPointF(a), QPointF(b), QPointF(c), QPointF(d)) for a, b, c, d in segments]


def _mid(a: QPointF, b: QPointF) -> QPointF:
    return QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)


class FreehandItem(VectorItem):
    """A freehand drawn path annotation item."""

    def __init__(self, parent: VectorItem | None = None) -> None:
        super().__init__(parent)
        self._path_points: list[QPointF] = []
        self._segments: list[BezierSegment] = []
        self._smoothing: float = DEFAULT_SMOOTHING
        self._is_closed: bool = False
        self._preview = QPainterPath()
        self._path = QPainterPath()
        # The long stroke's pieces (9.10): the bounds and the path of each completed
        # 500-point piece, the tail's path and bounds as floats, and the bounding
        # rectangle declared while the stroke is long, None otherwise
        self._piece_rects: list[QRectF] = []
        self._piece_paths: list[QPainterPath] = []
        self._tail_path = QPainterPath()
        self._tail_box: list[float] | None = None
        self._preview_bounds: QRectF | None = None
        # option.exposedRect is the repaint's own patch, which the long stroke's paint reads
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    # ------------------------------------------------------------ properties

    @property
    def path(self) -> QPainterPath:
        return QPainterPath(self._path)

    @property
    def points(self) -> list[tuple[float, float]]:
        """The raw points as pairs (the form earlier callers read)."""
        return [(p.x(), p.y()) for p in self._path_points]

    @property
    def path_points(self) -> list[QPointF]:
        """The raw sampled points in item coordinates (10.7), never changed by smoothing."""
        return [QPointF(p) for p in self._path_points]

    @property
    def bezier_segments(self) -> list[BezierSegment]:
        """The smoothed path as cubic segments (10.7): what is painted."""
        return _copy_segments(self._segments)

    @bezier_segments.setter
    def bezier_segments(self, value: list[BezierSegment]) -> None:
        self._segments = _copy_segments(list(value))
        self._rebuild_path()

    @property
    def smoothing(self) -> float:
        """The smoothing that produced the segments, 0.0 to 1.0 (10.7)."""
        return self._smoothing

    @smoothing.setter
    def smoothing(self, value: float) -> None:
        self._smoothing = _clamp_unit(value, DEFAULT_SMOOTHING)

    @property
    def smoothing_fit(self) -> tuple[float, list[BezierSegment]]:
        """The smoothing and the segments together: what a re-smooth changes, so its undo
        restores both exactly, a hand-edited segment included (9.7)."""
        return (self._smoothing, self.bezier_segments)

    @smoothing_fit.setter
    def smoothing_fit(self, value: tuple[float, list[BezierSegment]]) -> None:
        smoothing, segments = value
        self._smoothing = _clamp_unit(smoothing, DEFAULT_SMOOTHING)
        self.bezier_segments = segments

    @property
    def is_closed(self) -> bool:
        """Whether the last point joins the first and the fill is painted (9.6, 9.8)."""
        return self._is_closed

    @is_closed.setter
    def is_closed(self, value: bool) -> None:
        self._is_closed = bool(value)
        self._rebuild_path()

    # ------------------------------------------------------------ drawing and smoothing

    def add_point(self, point: QPointF) -> None:
        """Append a raw point while the stroke is drawn; the preview joins the points by
        quadratic curves through their midpoints (9.4). Past :data:`LONG_STROKE_POINTS`
        only the patch the point changed is repainted (9.10)."""
        p = QPointF(point)
        self._path_points.append(p)
        count = len(self._path_points)
        if count == 1:
            self._preview = QPainterPath()
            self._preview.moveTo(p)
            self._reset_pieces()
            self._tail_path.moveTo(p)
            self._tail_box = [p.x(), p.y(), p.x(), p.y()]
        else:
            prev = self._path_points[-2]
            node = _mid(prev, p)
            if count == 2:
                self._preview.lineTo(node)
                self._tail_path.lineTo(node)
            else:
                self._preview.quadTo(prev, node)
                self._tail_path.quadTo(prev, node)
            self._grow_tail_box(p)
            if (count - 1) % PREVIEW_PIECE_POINTS == 0:
                self._complete_piece(prev, p, node)
        if not self._long_stroke():
            self._rebuild_path()
            return
        if self._preview_bounds is None:
            # The stroke has just become long: one whole repaint, then patches
            self._preview_bounds = self._tight_bounding_rect().adjusted(
                -PREVIEW_BOUNDS_MARGIN,
                -PREVIEW_BOUNDS_MARGIN,
                PREVIEW_BOUNDS_MARGIN,
                PREVIEW_BOUNDS_MARGIN,
            )
            self._rebuild_path()
            return
        self._rebuild_path(patch=self._patch_of(self._path_points[-3:]))

    # ------------------------------------------------------------ the long stroke's pieces

    def _long_stroke(self) -> bool:
        """Whether the item is a long stroke being drawn (9.10): raw points past the
        threshold and no fitted segments yet."""
        return not self._segments and len(self._path_points) > LONG_STROKE_POINTS

    def _reset_pieces(self) -> None:
        self._piece_rects = []
        self._piece_paths = []
        self._tail_path = QPainterPath()
        self._tail_box = None
        self._preview_bounds = None

    def _grow_tail_box(self, p: QPointF) -> None:
        box = self._tail_box
        if box is None:
            self._tail_box = [p.x(), p.y(), p.x(), p.y()]
            return
        box[0] = min(box[0], p.x())
        box[1] = min(box[1], p.y())
        box[2] = max(box[2], p.x())
        box[3] = max(box[3], p.y())

    def _complete_piece(self, prev: QPointF, p: QPointF, node: QPointF) -> None:
        """The tail has reached a piece boundary at *p*: keep its path and bounds, and start
        the next piece at the node between *prev* and *p*, where the path passes."""
        box = self._tail_box or [p.x(), p.y(), p.x(), p.y()]
        self._piece_rects.append(QRectF(QPointF(box[0], box[1]), QPointF(box[2], box[3])))
        self._piece_paths.append(QPainterPath(self._tail_path))
        self._tail_path = QPainterPath()
        self._tail_path.moveTo(node)
        self._tail_box = [
            min(prev.x(), p.x()),
            min(prev.y(), p.y()),
            max(prev.x(), p.x()),
            max(prev.y(), p.y()),
        ]

    def _rebuild_pieces(self) -> None:
        """Recompute the pieces from the raw points (after a scale)."""
        points = self._path_points
        self._reset_pieces()
        for index, p in enumerate(points):
            if index == 0:
                self._tail_path.moveTo(p)
                self._tail_box = [p.x(), p.y(), p.x(), p.y()]
                continue
            prev = points[index - 1]
            node = _mid(prev, p)
            if index == 1:
                self._tail_path.lineTo(node)
            else:
                self._tail_path.quadTo(prev, node)
            self._grow_tail_box(p)
            if index % PREVIEW_PIECE_POINTS == 0:
                self._complete_piece(prev, p, node)

    def _cover(self, rect: QRectF) -> QRectF:
        """The pixels a piece of geometry within *rect* can touch: its stroke, its hit
        band's minimum, and its shadow."""
        margin = max(self.stroke_margin(), HIT_MIN_WIDTH / 2.0) + 2.0
        body = rect.adjusted(-margin, -margin, margin, margin)
        return body.united(self.shadow_rect(body))

    def _patch_of(self, points: list[QPointF]) -> QRectF:
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        return self._cover(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _pieces_touching(self, exposed: QRectF | None) -> list[tuple[int, int]]:
        """The runs of consecutive pieces, as (first, last) piece indexes with the tail as
        the last index, whose cover meets *exposed*; every piece when *exposed* is None."""
        count = len(self._piece_paths)
        tail_box = self._tail_box or [0.0, 0.0, 0.0, 0.0]
        tail_rect = QRectF(QPointF(tail_box[0], tail_box[1]), QPointF(tail_box[2], tail_box[3]))
        rects = [*self._piece_rects, tail_rect]
        runs: list[tuple[int, int]] = []
        for index in range(count + 1):
            if exposed is not None and not self._cover(rects[index]).intersects(exposed):
                continue
            if runs and runs[-1][1] == index - 1:
                runs[-1] = (runs[-1][0], index)
            else:
                runs.append((index, index))
        return runs

    def _preview_path_for(self, exposed: QRectF | None) -> QPainterPath:
        """The preview's pieces that meet *exposed*, consecutive pieces joined as one
        subpath so the stroke shows no seam where they meet, the tail ending at the last
        point as the whole preview does."""
        count = len(self._piece_paths)
        runs = self._pieces_touching(exposed)
        if runs == [(0, count)]:
            # Every piece: the whole preview, already built, rather than the pieces rejoined
            return QPainterPath(self._path)
        path = QPainterPath()
        for first, last in runs:
            for index in range(first, last + 1):
                piece = self._piece_paths[index] if index < count else self._tail_path
                if index == first:
                    path.addPath(piece)
                else:
                    path.connectPath(piece)
            if last == count and len(self._path_points) > 1:
                path.lineTo(self._path_points[-1])
        return path

    def preview_snapshot(self) -> PreviewSnapshot:
        """The raw points, the preview path, and the long stroke's pieces as they stand,
        to be restored later.

        Shift's straight segments (9.5) replace the segment being drawn on every move
        rather than appending to it. The tool takes one snapshot when Shift is first
        held and restores it before each move, which costs a list copy rather than a
        replay of every point through :meth:`add_point`.
        """
        pieces = (
            list(self._piece_rects),
            list(self._piece_paths),
            QPainterPath(self._tail_path),
            list(self._tail_box) if self._tail_box is not None else None,
            QRectF(self._preview_bounds) if self._preview_bounds is not None else None,
        )
        return ([QPointF(p) for p in self._path_points], QPainterPath(self._preview), pieces)

    def restore_preview(self, snapshot: PreviewSnapshot) -> None:
        """Put the stroke back to a :meth:`preview_snapshot`; the snapshot stays usable.
        A long stroke repaints only the patch the dropped points covered."""
        points, preview, pieces = snapshot
        dropped = self._path_points[max(len(points) - 2, 0) :]
        self._path_points = list(points)
        self._preview = QPainterPath(preview)
        rects, paths, tail_path, tail_box, bounds = pieces
        self._piece_rects = list(rects)
        self._piece_paths = list(paths)
        self._tail_path = QPainterPath(tail_path)
        self._tail_box = list(tail_box) if tail_box is not None else None
        self._preview_bounds = QRectF(bounds) if bounds is not None else None
        if self._long_stroke() and self._preview_bounds is not None and dropped:
            self._rebuild_path(patch=self._patch_of(dropped))
        else:
            self._rebuild_path()

    def noise_floor(self) -> float:
        """The least fitting error the raw points allow: their noise times
        :data:`NOISE_FLOOR_FACTOR`, never past :data:`NOISE_FLOOR_MAX_PX`."""
        return min(NOISE_FLOOR_FACTOR * stroke_noise(self._path_points), NOISE_FLOOR_MAX_PX)

    def fit_error(self, smoothing: float) -> float:
        """Stage 2's fitting error at *smoothing* (9.3): smoothing times 3 px, never below
        half a pixel and never below the stroke's noise floor."""
        smoothing = _clamp_unit(smoothing, DEFAULT_SMOOTHING)
        return max(smoothing * SMOOTHING_ERROR_PX, MIN_FIT_ERROR_PX, self.noise_floor())

    def smoothed_points(self, smoothing: float) -> list[QPointF]:
        """The raw points after the averaging stage at *smoothing* (decision 4): the reach
        is *smoothing* times :data:`SMOOTHING_REACH_PX`; at 0 percent the raw points."""
        smoothing = _clamp_unit(smoothing, DEFAULT_SMOOTHING)
        return travel_average(self._path_points, smoothing * SMOOTHING_REACH_PX)

    def fit_segments(self, smoothing: float) -> list[BezierSegment]:
        """The segments the pipeline gives for the raw points at *smoothing*: the averaging
        stage of decision 4, then the two stages of 9.3."""
        smoothing = _clamp_unit(smoothing, DEFAULT_SMOOTHING)
        points = self.smoothed_points(smoothing)
        kept = simplify_rdp_indices(points, SIMPLIFY_TOLERANCE_PX)
        if len(kept) < 2:
            return []
        # The fit's end tangents come from the stroke around each kept point rather than
        # from the kept neighbours (decision 4)
        return fit_cubic_beziers(
            [points[i] for i in kept], self.fit_error(smoothing), point_tangents(points, kept)
        )

    def smooth(self, smoothing: float | None = None) -> None:
        """Run the pipeline from the raw points and paint its segments (9.3, 9.7)."""
        if smoothing is not None:
            self._smoothing = _clamp_unit(smoothing, DEFAULT_SMOOTHING)
        self._segments = self.fit_segments(self._smoothing)
        self._rebuild_path()

    def _rebuild_path(self, *, patch: QRectF | None = None) -> None:
        """Rebuild the painted path. With *patch*, a long stroke's move, only that patch is
        repainted and the declared bounding rectangle grows when the patch leaves it;
        without it the geometry changed and the whole item repaints."""
        path = QPainterPath()
        if self._segments:
            path.moveTo(self._segments[0][0])
            for _start, cp1, cp2, end in self._segments:
                path.cubicTo(cp1, cp2, end)
        elif self._path_points:
            path = QPainterPath(self._preview)
            if len(self._path_points) > 1:
                path.lineTo(self._path_points[-1])
        if self._is_closed and path.elementCount() > 1:
            path.closeSubpath()
        self._path = path
        if not self._long_stroke():
            self._preview_bounds = None
        bounds = self._preview_bounds
        if patch is None or bounds is None:
            self._geometry_changed()
            return
        if not bounds.contains(patch):
            self._preview_bounds = bounds.united(patch).adjusted(
                -PREVIEW_BOUNDS_MARGIN,
                -PREVIEW_BOUNDS_MARGIN,
                PREVIEW_BOUNDS_MARGIN,
                PREVIEW_BOUNDS_MARGIN,
            )
            self._geometry_changed()
            return
        self.update(patch)

    # ------------------------------------------------------------ geometry

    def scale_geometry(self, sx: float, sy: float) -> None:
        super().scale_geometry(sx, sy)

        def scaled(p: QPointF) -> QPointF:
            return QPointF(p.x() * sx, p.y() * sy)

        self._path_points = [scaled(p) for p in self._path_points]
        self._segments = [
            (scaled(a), scaled(b), scaled(c), scaled(d)) for a, b, c, d in self._segments
        ]
        self._preview = QPainterPath()
        for i, p in enumerate(self._path_points):
            if i == 0:
                self._preview.moveTo(p)
            elif i == 1:
                self._preview.lineTo(_mid(self._path_points[0], p))
            else:
                prev = self._path_points[i - 1]
                self._preview.quadTo(prev, _mid(prev, p))
        self._rebuild_pieces()
        self._rebuild_path()

    def _tight_bounding_rect(self) -> QRectF:
        return self._cover(self._path.boundingRect())

    def boundingRect(self) -> QRectF:
        if self._preview_bounds is not None and self._long_stroke():
            return QRectF(self._preview_bounds)
        return self._tight_bounding_rect()

    def geometry_rect(self) -> QRectF:
        return self._path.boundingRect()

    def shape(self) -> QPainterPath:
        """The stroke's band, stroke width plus 4 px and never under 8 px, and the inside
        of a closed stroke with a fill (9.9)."""
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._stroke_width + self.HIT_PADDING, HIT_MIN_WIDTH))
        band = stroker.createStroke(self._path)
        if self._is_closed and self._fill_color.alpha() > 0:
            return band.united(self._path)
        return band

    def paint(self, painter: QPainter | None, option: Any, widget: Any = None) -> None:
        if painter is None:
            return
        if self._long_stroke():
            # 9.10: only the pieces the repaint touches, as one path (decision 3, option B)
            exposed = option.exposedRect if option is not None else None
            path = self._preview_path_for(exposed)
            self._apply_flip(painter)
            self.paint_shadow(painter, self.shadow_path(path, closed=False))
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            self._end_flip(painter)
            return
        self._apply_flip(painter)
        self.paint_shadow(painter, self.shadow_path(self._path, closed=self._is_closed))
        painter.setPen(self.pen())
        if self._is_closed:
            painter.setBrush(self.brush())
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)
        self._end_flip(painter)

    # ------------------------------------------------------------ creation defaults

    def apply_creation_defaults(self, defaults: dict[str, Any]) -> None:
        super().apply_creation_defaults(defaults)
        if "smoothing" in defaults:
            # The tool keeps the Smoothing slider's whole percent (notes Section 2.4)
            self._smoothing = _clamp_unit(float(defaults["smoothing"]) / 100.0)
        if "close_path" in defaults:
            self._is_closed = bool(defaults["close_path"])
        self._rebuild_path()

    # ------------------------------------------------------------ serialization

    def serialize(self) -> dict[str, Any]:
        data = self._base_data()
        data["type"] = "FreehandItem"
        data["path_points"] = [_point_data(p) for p in self._path_points]
        data["bezier_segments"] = [
            {
                "start": _point_data(a),
                "cp1": _point_data(b),
                "cp2": _point_data(c),
                "end": _point_data(d),
            }
            for a, b, c, d in self._segments
        ]
        data["smoothing"] = self._smoothing
        data["is_closed"] = self._is_closed
        data["pressure_data"] = None
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> FreehandItem:
        item = cls()
        item._apply_base_data(data)
        item._smoothing = _clamp_unit(data.get("smoothing", DEFAULT_SMOOTHING), DEFAULT_SMOOTHING)
        item._is_closed = bool(data.get("is_closed", False))
        # 10.7's path_points; a file saved before this work has the simplified polyline
        # under points, which becomes the raw points (notes Section 2.4)
        raw = data.get("path_points", data.get("points", []))
        for entry in raw if isinstance(raw, list) else []:
            point = _point(entry)
            if point is not None:
                item.add_point(point)
        segments: list[BezierSegment] = []
        for entry in data.get("bezier_segments") or []:
            if not isinstance(entry, dict):
                continue
            parts = [_point(entry.get(k)) for k in ("start", "cp1", "cp2", "end")]
            if all(p is not None for p in parts):
                a, b, c, d = parts
                assert a is not None and b is not None and c is not None and d is not None
                segments.append((a, b, c, d))
        if segments:
            item.bezier_segments = segments
        else:
            item.smooth()
        return item
