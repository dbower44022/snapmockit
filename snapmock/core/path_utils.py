"""Path utilities — point simplification and smoothing algorithms."""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF


def _perpendicular_distance(point: QPointF, line_start: QPointF, line_end: QPointF) -> float:
    """Compute the perpendicular distance from *point* to the line (start→end)."""
    dx = line_end.x() - line_start.x()
    dy = line_end.y() - line_start.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(point.x() - line_start.x(), point.y() - line_start.y())
    t = ((point.x() - line_start.x()) * dx + (point.y() - line_start.y()) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    proj_x = line_start.x() + t * dx
    proj_y = line_start.y() + t * dy
    return math.hypot(point.x() - proj_x, point.y() - proj_y)


def constrain_angle(origin: QPointF, point: QPointF, step_degrees: float = 15.0) -> QPointF:
    """*point* moved onto the nearest ray from *origin* at a multiple of *step_degrees*,
    at its own distance from *origin* (Basic Shape PRD 3.2: Shift while drawing a line)."""
    dx = point.x() - origin.x()
    dy = point.y() - origin.y()
    length = math.hypot(dx, dy)
    if length == 0.0:
        return QPointF(point)
    angle = math.degrees(math.atan2(dy, dx))
    snapped = math.radians(round(angle / step_degrees) * step_degrees)
    return QPointF(
        origin.x() + length * math.cos(snapped), origin.y() + length * math.sin(snapped)
    )


def constrained_rect(
    origin: QPointF, current: QPointF, *, square: bool = False, from_centre: bool = False
) -> QRectF:
    """The rectangle a drag from *origin* to *current* defines under 2.3's modifiers.

    With neither modifier the two points are opposite corners, which is what every
    shape tool drew before. ``square`` (Shift) makes both sides the longer of the two
    the drag spans, so the square follows the cursor's dominant direction and keeps
    the corner at *origin*. ``from_centre`` (Alt, or Ctrl by decision 4) makes *origin*
    the centre and the drag the half-diagonal, so the rectangle grows outward on every
    side at once. Both together give a square centred on *origin*.
    """
    dx = current.x() - origin.x()
    dy = current.y() - origin.y()
    if square:
        side = max(abs(dx), abs(dy))
        dx = math.copysign(side, dx) if dx else side
        dy = math.copysign(side, dy) if dy else side
    if from_centre:
        return QRectF(
            origin.x() - abs(dx), origin.y() - abs(dy), 2 * abs(dx), 2 * abs(dy)
        ).normalized()
    return QRectF(origin, QPointF(origin.x() + dx, origin.y() + dy)).normalized()


_RDP_NUMPY_SPAN = 24
"""A span with fewer interior points than this is measured in Python: below it NumPy's
per-call cost outweighs the loop, and a long stroke's simplification is mostly short
spans (Freehand remainder notes, Section 6)."""


def simplify_rdp(points: list[QPointF], epsilon: float = 2.0) -> list[QPointF]:
    """Simplify a polyline using the Ramer-Douglas-Peucker algorithm.

    Iterative, so a stroke of thousands of points cannot exhaust the recursion limit.
    Each span's distances are measured in one NumPy pass once the span is long enough
    for that to pay, and in a plain loop below that, so a 5000-point stroke simplifies
    in a few milliseconds (Basic Shape PRD 9.10; Freehand remainder decision 2).

    Parameters
    ----------
    points : list[QPointF]
        The input polyline.
    epsilon : float
        Maximum deviation threshold.  Larger values produce more simplification.

    Returns
    -------
    list[QPointF]
        The simplified polyline.
    """
    return [points[i] for i in simplify_rdp_indices(points, epsilon)]


def simplify_rdp_indices(points: list[QPointF], epsilon: float = 2.0) -> list[int]:
    """The indexes into *points* that :func:`simplify_rdp` keeps, in order, so a caller
    can read the raw stroke around each kept point (:func:`point_tangents`)."""
    count = len(points)
    if count <= 2:
        return list(range(count))
    xs = np.fromiter((p.x() for p in points), dtype=float, count=count)
    ys = np.fromiter((p.y() for p in points), dtype=float, count=count)
    xl: list[float] = xs.tolist()
    yl: list[float] = ys.tolist()
    keep = [False] * count
    keep[0] = keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        sx, sy = xl[first], yl[first]
        dx = xl[last] - sx
        dy = yl[last] - sy
        length_sq = dx * dx + dy * dy
        if last - first - 1 < _RDP_NUMPY_SPAN:
            max_dist = 0.0
            max_idx = first
            for i in range(first + 1, last):
                px, py = xl[i], yl[i]
                if length_sq == 0:
                    d = math.hypot(px - sx, py - sy)
                else:
                    t = ((px - sx) * dx + (py - sy) * dy) / length_sq
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    d = math.hypot(px - (sx + t * dx), py - (sy + t * dy))
                if d > max_dist:
                    max_dist = d
                    max_idx = i
        else:
            px_arr = xs[first + 1 : last]
            py_arr = ys[first + 1 : last]
            if length_sq == 0:
                dist = np.hypot(px_arr - sx, py_arr - sy)
            else:
                t_arr = ((px_arr - sx) * dx + (py_arr - sy) * dy) / length_sq
                np.clip(t_arr, 0.0, 1.0, out=t_arr)
                dist = np.hypot(px_arr - (sx + t_arr * dx), py_arr - (sy + t_arr * dy))
            at = int(np.argmax(dist))
            max_dist = float(dist[at])
            max_idx = first + 1 + at
        if max_dist > epsilon:
            keep[max_idx] = True
            stack.append((first, max_idx))
            stack.append((max_idx, last))
    return [i for i, k in enumerate(keep) if k]


TANGENT_WINDOW = 8
"""How many raw points either side of a kept point :func:`point_tangents` averages: at
the mouse's 60 to 120 Hz, about a tenth of a second of travel each way."""


def point_tangents(points: list[QPointF], indices: list[int]) -> list[np.ndarray | None]:
    """The direction of travel of the stroke *points* at each kept index, as unit vectors,
    read from the raw points on either side rather than from the kept neighbours.

    Schneider's fit estimates a piece's end tangents from the chord to the next kept
    point, which is right when the kept points are dense and wrong when a wide
    simplification leaves them far apart: a wavy underline at 50 percent smoothing then
    looped after its first trough (Freehand remainder notes, Section 8.9). The mean of the
    raw points up to :data:`TANGENT_WINDOW` before a kept point to the mean of those after
    it is the stroke's own direction there. None where the stroke does not move, so the
    fit falls back to the chord.
    """
    a = np.array([[p.x(), p.y()] for p in points], dtype=float).reshape(-1, 2)
    count = len(a)
    out: list[np.ndarray | None] = []
    for i in indices:
        lo = max(0, i - TANGENT_WINDOW)
        hi = min(count - 1, i + TANGENT_WINDOW)
        before = a[lo:i].mean(axis=0) if i > lo else a[i]
        after = a[i + 1 : hi + 1].mean(axis=0) if hi > i else a[i]
        v = after - before
        length = float(np.hypot(v[0], v[1]))
        out.append(v / length if length > 1e-9 else None)
    return out


BezierSegment = tuple[QPointF, QPointF, QPointF, QPointF]
"""One cubic Bezier segment: start, first control point, second control point, end."""

MAX_HANDLE_CHORDS = 2.0
"""A fitted piece's control handles are never longer than this many times its chord: a
half circle needs two thirds of a chord, and anything past two chords is the least-squares
solve running away on a zigzag (Freehand remainder notes, Section 8.6)."""


def _normalized(v: np.ndarray) -> np.ndarray:
    length = float(np.hypot(v[0], v[1]))
    return v / length if length > 1e-12 else np.zeros(2)


def _bernstein(u: np.ndarray) -> np.ndarray:
    """The four cubic Bernstein polynomials at the parameters *u*, one row per parameter,
    built once per piece and shared by the fit, the error, and the reparameterization.
    The expressions are written as Schneider's fit always wrote them, so the values are
    the ones the fit produced before the basis was shared."""
    m = 1.0 - u
    return np.stack([m**3, 3 * m * m * u, 3 * m * u * u, u**3], axis=1)


def _bezier(bez: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Points of the cubic *bez* (4 by 2) at the parameters *u*."""
    result: np.ndarray = _bernstein(u) @ bez
    return result


def _generate_bezier(
    pts: np.ndarray, basis: np.ndarray, t1: np.ndarray, t2: np.ndarray
) -> np.ndarray:
    """The least-squares cubic through *pts* with the Bernstein rows *basis* and the end
    tangents *t1* and *t2*."""
    first, last = pts[0], pts[-1]
    b0, b1, b2, b3 = basis[:, 0], basis[:, 1], basis[:, 2], basis[:, 3]
    a1 = np.outer(b1, t1)
    a2 = np.outer(b2, t2)
    c00 = float(np.sum(a1 * a1))
    c01 = float(np.sum(a1 * a2))
    c11 = float(np.sum(a2 * a2))
    tmp = pts - np.outer(b0 + b1, first) - np.outer(b2 + b3, last)
    x0 = float(np.sum(a1 * tmp))
    x1 = float(np.sum(a2 * tmp))
    det = c00 * c11 - c01 * c01
    seg_length = float(np.hypot(*(last - first)))
    alpha_l = (x0 * c11 - x1 * c01) / det if abs(det) > 1e-12 else 0.0
    alpha_r = (c00 * x1 - c01 * x0) / det if abs(det) > 1e-12 else 0.0
    epsilon = 1e-6 * seg_length
    # Schneider's fallback for a degenerate solve, and the runaway guard of 09-13-26: a
    # piece whose points zigzag (a shaky hand through a wide simplification) can solve
    # to handles thousands of pixels long that still pass every point at its own
    # parameter, and the curve loops across the canvas between them. Such a piece takes
    # the chord-third heuristic and is split by the error test like any other miss.
    runaway = seg_length > 0.0 and max(alpha_l, alpha_r) > MAX_HANDLE_CHORDS * seg_length
    if alpha_l < epsilon or alpha_r < epsilon or runaway:
        alpha_l = alpha_r = seg_length / 3.0
    return np.array([first, first + t1 * alpha_l, last + t2 * alpha_r, last])


def _reparameterize(pts: np.ndarray, u: np.ndarray, bez: np.ndarray, q: np.ndarray) -> np.ndarray:
    """One Newton-Raphson step toward each point's nearest parameter on *bez*, whose
    points at *u* are already known as *q*."""
    d1 = 3.0 * (bez[1:] - bez[:-1])
    d2 = 2.0 * (d1[1:] - d1[:-1])
    m = 1.0 - u
    q1 = np.outer(m * m, d1[0]) + np.outer(2 * m * u, d1[1]) + np.outer(u * u, d1[2])
    q2 = np.outer(m, d2[0]) + np.outer(u, d2[1])
    diff = q - pts
    numerator = np.sum(diff * q1, axis=1)
    denominator = np.sum(q1 * q1, axis=1) + np.sum(diff * q2, axis=1)
    safe = np.abs(denominator) > 1e-12
    step = np.zeros_like(u)
    step[safe] = numerator[safe] / denominator[safe]
    result: np.ndarray = np.clip(u - step, 0.0, 1.0)
    return result


def fit_cubic_beziers(
    points: list[QPointF], error: float, tangents: list[np.ndarray | None] | None = None
) -> list[BezierSegment]:
    """Cubic Bezier segments through *points*, each within *error* pixels of the points it
    covers: least-squares fitting with Newton reparameterization, split at the worst point
    when a piece misses (Schneider, "An Algorithm for Automatically Fitting Digitized
    Curves", Graphics Gems, 1990). Basic Shape PRD 9.3, stage 2.

    *tangents*, one unit direction of travel per point or None, replaces Schneider's chord
    estimate of a piece's end tangents where given (:func:`point_tangents`)."""
    pts = np.array([[p.x(), p.y()] for p in points], dtype=float).reshape(-1, 2)
    dirs: list[np.ndarray | None] = list(tangents) if tangents is not None else [None] * len(pts)
    if len(pts) > 1:
        moved = np.ones(len(pts), dtype=bool)
        moved[1:] = np.any(np.abs(np.diff(pts, axis=0)) > 1e-9, axis=1)
        pts = pts[moved]
        dirs = [d for d, m in zip(dirs, moved) if m]
    if len(pts) == 0:
        return []
    if len(pts) == 1:
        p = QPointF(float(pts[0][0]), float(pts[0][1]))
        return [(p, QPointF(p), QPointF(p), QPointF(p))]
    error_sq = max(error, 1e-3) ** 2
    out: list[np.ndarray] = []

    def travel(index: int, fallback: np.ndarray) -> np.ndarray:
        d = dirs[index]
        return d if d is not None else fallback

    first_t = travel(0, _normalized(pts[1] - pts[0]))
    last_t = -travel(len(pts) - 1, -_normalized(pts[-2] - pts[-1]))
    stack = [(0, len(pts) - 1, first_t, last_t)]
    while stack:
        first, last, t1, t2 = stack.pop()
        piece = pts[first : last + 1]
        if len(piece) == 2:
            dist = float(np.hypot(*(piece[1] - piece[0]))) / 3.0
            out.append(np.array([piece[0], piece[0] + t1 * dist, piece[1] + t2 * dist, piece[1]]))
            continue
        chords = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(piece, axis=0).T))])
        u = chords / chords[-1] if chords[-1] > 0 else np.linspace(0.0, 1.0, len(piece))
        basis = _bernstein(u)
        bez = _generate_bezier(piece, basis, t1, t2)
        q = basis @ bez
        dist_sq = np.sum((q - piece) ** 2, axis=1)
        worst = float(dist_sq.max())
        if worst < error_sq:
            out.append(bez)
            continue
        if worst < error_sq * 4.0:
            for _ in range(20):
                u = _reparameterize(piece, u, bez, q)
                basis = _bernstein(u)
                bez = _generate_bezier(piece, basis, t1, t2)
                q = basis @ bez
                dist_sq = np.sum((q - piece) ** 2, axis=1)
                worst = float(dist_sq.max())
                if worst < error_sq:
                    break
            if worst < error_sq:
                out.append(bez)
                continue
        split = int(np.argmax(dist_sq[1:-1])) + 1
        centre = -travel(first + split, -_normalized(piece[split - 1] - piece[split + 1]))
        stack.append((first + split, last, -centre, t2))
        stack.append((first, first + split, t1, centre))
    return [
        (
            QPointF(float(b[0][0]), float(b[0][1])),
            QPointF(float(b[1][0]), float(b[1][1])),
            QPointF(float(b[2][0]), float(b[2][1])),
            QPointF(float(b[3][0]), float(b[3][1])),
        )
        for b in out
    ]


def travel_average(points: list[QPointF], reach: float) -> list[QPointF]:
    """*points* smoothed by a centred moving average over the points within *reach* pixels
    of travel along the stroke on either side; the first and last points stay put
    (Basic Shape PRD 9.3 as decision 4 of the Freehand remainder work reshaped it).

    The window is measured in travel and not in points, so the result does not depend
    on the mouse's event rate: a hand tremor a few pixels long is averaged away at a
    reach of a few tens of pixels, and a shape larger than the reach keeps its size to
    within a few pixels. A reach of zero returns the points unchanged.
    """
    count = len(points)
    if reach <= 0.0 or count < 3:
        return [QPointF(p) for p in points]
    a = np.array([[p.x(), p.y()] for p in points], dtype=float)
    travel = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(a, axis=0).T))])
    lo = np.searchsorted(travel, travel - reach, side="left")
    hi = np.searchsorted(travel, travel + reach, side="right")
    sums = np.vstack([[0.0, 0.0], np.cumsum(a, axis=0)])
    out = (sums[hi] - sums[lo]) / (hi - lo)[:, None]
    out[0] = a[0]
    out[-1] = a[-1]
    return [QPointF(float(x), float(y)) for x, y in out]


def stroke_noise(points: list[QPointF]) -> float:
    """How much of a stroke's point-to-point wobble is noise rather than curve, in pixels
    (Basic Shape PRD 9.3, 9.10; Freehand remainder decision 2, option B).

    Each interior point's signed distance from the chord through its two neighbours is a
    deviation. A curve's deviations change slowly from one point to the next; noise, the
    whole-pixel rounding of mouse coordinates or a shaky hand, makes them jump. The
    measure is the median jump between consecutive deviations: near zero for a smooth
    stroke or a circle, about 0.45 px for half a pixel of jitter on both axes, about
    0.75 px for a stroke rounded to whole pixels. Fewer than four points have no noise.
    """
    if len(points) < 4:
        return 0.0
    a = np.array([[p.x(), p.y()] for p in points], dtype=float)
    before, at, after = a[:-2], a[1:-1], a[2:]
    chord = after - before
    length = np.hypot(chord[:, 0], chord[:, 1])
    length[length == 0.0] = 1.0
    deviation = (
        (at[:, 0] - before[:, 0]) * chord[:, 1] - (at[:, 1] - before[:, 1]) * chord[:, 0]
    ) / length
    return float(np.median(np.abs(np.diff(deviation))))


def moving_average(points: list[QPointF], window: int) -> list[QPointF]:
    """*points* smoothed by a moving average over the last *window* points (Blur PRD 3.2).

    Each point is replaced by the mean of itself and the points before it, at most *window*
    in all, so the stroke smooths as it is drawn without waiting for the release. The first
    point is never moved, so the stroke starts where the press did.
    """
    if window <= 1 or len(points) < 2:
        return [QPointF(p) for p in points]
    smoothed = [QPointF(points[0])]
    for index in range(1, len(points)):
        run = points[max(0, index - window + 1) : index + 1]
        x = sum(p.x() for p in run) / len(run)
        y = sum(p.y() for p in run) / len(run)
        smoothed.append(QPointF(x, y))
    return smoothed


def path_length(points: list[QPointF]) -> float:
    """The length of the polyline through *points*."""
    return sum(QLineF(points[i], points[i + 1]).length() for i in range(len(points) - 1))


def straightness(points: list[QPointF]) -> float:
    """Arc length over the straight-line distance from the first point to the last (3.3).

    1.0 is a perfect straight line; a stroke that ends where it began has no straight-line
    distance at all and gives infinity, so it is never straightened.
    """
    if len(points) < 2:
        return 1.0
    direct = QLineF(points[0], points[-1]).length()
    if direct < 1e-9:
        return float("inf")
    return path_length(points) / direct


def snap_to_axis(start: QPointF, end: QPointF, degrees: float) -> QPointF:
    """*end* pulled onto the horizontal or vertical through *start* when it lies within
    *degrees* of one, keeping its distance (3.3)."""
    line = QLineF(start, end)
    if line.length() < 1e-9:
        return QPointF(end)
    angle = line.angle() % 90.0
    if angle > 90.0 - degrees or angle < degrees:
        snapped = QLineF(line)
        snapped.setAngle(round(line.angle() / 90.0) * 90.0)
        return snapped.p2()
    return QPointF(end)
