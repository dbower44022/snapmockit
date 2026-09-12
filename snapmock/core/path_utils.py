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


def simplify_rdp(points: list[QPointF], epsilon: float = 2.0) -> list[QPointF]:
    """Simplify a polyline using the Ramer-Douglas-Peucker algorithm.

    Iterative, so a stroke of thousands of points cannot exhaust the recursion limit.

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
    if len(points) <= 2:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        max_dist = 0.0
        max_idx = first
        for i in range(first + 1, last):
            d = _perpendicular_distance(points[i], points[first], points[last])
            if d > max_dist:
                max_dist = d
                max_idx = i
        if max_dist > epsilon:
            keep[max_idx] = True
            stack.append((first, max_idx))
            stack.append((max_idx, last))
    return [p for p, k in zip(points, keep) if k]


BezierSegment = tuple[QPointF, QPointF, QPointF, QPointF]
"""One cubic Bezier segment: start, first control point, second control point, end."""


def _normalized(v: np.ndarray) -> np.ndarray:
    length = float(np.hypot(v[0], v[1]))
    return v / length if length > 1e-12 else np.zeros(2)


def _bezier(bez: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Points of the cubic *bez* (4 by 2) at the parameters *u*."""
    m = 1.0 - u
    b = np.stack([m**3, 3 * m * m * u, 3 * m * u * u, u**3], axis=1)
    result: np.ndarray = b @ bez
    return result


def _generate_bezier(pts: np.ndarray, u: np.ndarray, t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """The least-squares cubic through *pts* at *u* with end tangents *t1* and *t2*."""
    first, last = pts[0], pts[-1]
    m = 1.0 - u
    b0, b1, b2, b3 = m**3, 3 * m * m * u, 3 * m * u * u, u**3
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
    if alpha_l < epsilon or alpha_r < epsilon:
        alpha_l = alpha_r = seg_length / 3.0
    return np.array([first, first + t1 * alpha_l, last + t2 * alpha_r, last])


def _reparameterize(pts: np.ndarray, u: np.ndarray, bez: np.ndarray) -> np.ndarray:
    """One Newton-Raphson step toward each point's nearest parameter on *bez*."""
    q = _bezier(bez, u)
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


def fit_cubic_beziers(points: list[QPointF], error: float) -> list[BezierSegment]:
    """Cubic Bezier segments through *points*, each within *error* pixels of the points it
    covers: least-squares fitting with Newton reparameterization, split at the worst point
    when a piece misses (Schneider, "An Algorithm for Automatically Fitting Digitized
    Curves", Graphics Gems, 1990). Basic Shape PRD 9.3, stage 2."""
    pts = np.array([[p.x(), p.y()] for p in points], dtype=float).reshape(-1, 2)
    if len(pts) > 1:
        moved = np.ones(len(pts), dtype=bool)
        moved[1:] = np.any(np.abs(np.diff(pts, axis=0)) > 1e-9, axis=1)
        pts = pts[moved]
    if len(pts) == 0:
        return []
    if len(pts) == 1:
        p = QPointF(float(pts[0][0]), float(pts[0][1]))
        return [(p, QPointF(p), QPointF(p), QPointF(p))]
    error_sq = max(error, 1e-3) ** 2
    out: list[np.ndarray] = []
    stack = [(0, len(pts) - 1, _normalized(pts[1] - pts[0]), _normalized(pts[-2] - pts[-1]))]
    while stack:
        first, last, t1, t2 = stack.pop()
        piece = pts[first : last + 1]
        if len(piece) == 2:
            dist = float(np.hypot(*(piece[1] - piece[0]))) / 3.0
            out.append(np.array([piece[0], piece[0] + t1 * dist, piece[1] + t2 * dist, piece[1]]))
            continue
        chords = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(piece, axis=0).T))])
        u = chords / chords[-1] if chords[-1] > 0 else np.linspace(0.0, 1.0, len(piece))
        bez = _generate_bezier(piece, u, t1, t2)
        dist_sq = np.sum((_bezier(bez, u) - piece) ** 2, axis=1)
        if float(dist_sq.max()) < error_sq:
            out.append(bez)
            continue
        if float(dist_sq.max()) < error_sq * 4.0:
            for _ in range(20):
                u = _reparameterize(piece, u, bez)
                bez = _generate_bezier(piece, u, t1, t2)
                dist_sq = np.sum((_bezier(bez, u) - piece) ** 2, axis=1)
                if float(dist_sq.max()) < error_sq:
                    break
            if float(dist_sq.max()) < error_sq:
                out.append(bez)
                continue
        split = int(np.argmax(dist_sq[1:-1])) + 1
        centre = _normalized(piece[split - 1] - piece[split + 1])
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
