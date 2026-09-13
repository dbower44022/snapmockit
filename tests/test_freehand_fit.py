"""The Freehand pipeline's cost on release (Basic Shape PRD 9.3, 9.10; Freehand remainder
decision 2). The reference functions below are the pipeline as it stood before the work
(commit c1ee66c), kept here so the faster pipeline is shown to give the same result on the
strokes the pipeline tests use; the timing tests hold loose ceilings, and the measured
figures are in the notes (docs/Freehand-Remainder-Implementation.md, Section 6)."""

from __future__ import annotations

import math
import random
import time

import numpy as np
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from snapmock.core.path_utils import BezierSegment, fit_cubic_beziers, simplify_rdp
from snapmock.items.freehand_item import FreehandItem

FIT_CEILING_MS = 200.0
"""Four times 9.10's 50 ms, for a machine shared with a full-suite run; measured alone,
the whole pipeline takes 13 to 20 ms at 5000 points (notes Section 6)."""


# ---------------------------------------------------------------- the strokes


def _sine(count: int, *, jitter: bool = False, quantise: bool = False) -> list[QPointF]:
    """The notes' stroke: a sine wave 2800 px across, 150 px high, jittered by half a pixel
    either way on both axes, or rounded to whole pixels as a mouse at 100 percent gives."""
    rnd = random.Random(1)
    points = []
    for i in range(count):
        x = 2800.0 * i / (count - 1)
        y = 200.0 + 150.0 * math.sin(x / 60.0)
        if jitter:
            x += rnd.uniform(-0.5, 0.5)
            y += rnd.uniform(-0.5, 0.5)
        if quantise:
            x, y = float(round(x)), float(round(y))
        points.append(QPointF(x, y))
    return points


def _wavy(count: int = 300) -> list[QPointF]:
    return [QPointF(i, 30 * math.sin(i / 25.0) + (i % 2) * 0.8) for i in range(count)]


def _circle(radius: float = 50.0, count: int = 90) -> list[QPointF]:
    return [
        QPointF(
            60 + radius * math.cos(2 * math.pi * k / count),
            60 + radius * math.sin(2 * math.pi * k / count),
        )
        for k in range(count)
    ]


def _random_walk(seed: int, count: int) -> list[QPointF]:
    rnd = random.Random(seed)
    x = y = 0.0
    points = []
    for _ in range(count):
        x += rnd.uniform(-3.0, 5.0)
        y += rnd.uniform(-4.0, 4.0)
        points.append(QPointF(x, y))
    return points


# ---------------------------------------------------------------- the reference pipeline


def _ref_perpendicular_distance(point: QPointF, line_start: QPointF, line_end: QPointF) -> float:
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


def _ref_simplify_rdp(points: list[QPointF], epsilon: float = 2.0) -> list[QPointF]:
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
            d = _ref_perpendicular_distance(points[i], points[first], points[last])
            if d > max_dist:
                max_dist = d
                max_idx = i
        if max_dist > epsilon:
            keep[max_idx] = True
            stack.append((first, max_idx))
            stack.append((max_idx, last))
    return [p for p, k in zip(points, keep) if k]


def _ref_normalized(v: np.ndarray) -> np.ndarray:
    length = float(np.hypot(v[0], v[1]))
    return v / length if length > 1e-12 else np.zeros(2)


def _ref_bezier(bez: np.ndarray, u: np.ndarray) -> np.ndarray:
    m = 1.0 - u
    b = np.stack([m**3, 3 * m * m * u, 3 * m * u * u, u**3], axis=1)
    result: np.ndarray = b @ bez
    return result


def _ref_generate_bezier(
    pts: np.ndarray, u: np.ndarray, t1: np.ndarray, t2: np.ndarray
) -> np.ndarray:
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


def _ref_reparameterize(pts: np.ndarray, u: np.ndarray, bez: np.ndarray) -> np.ndarray:
    q = _ref_bezier(bez, u)
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


def _ref_fit_cubic_beziers(points: list[QPointF], error: float) -> list[BezierSegment]:
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
    stack = [
        (0, len(pts) - 1, _ref_normalized(pts[1] - pts[0]), _ref_normalized(pts[-2] - pts[-1]))
    ]
    while stack:
        first, last, t1, t2 = stack.pop()
        piece = pts[first : last + 1]
        if len(piece) == 2:
            dist = float(np.hypot(*(piece[1] - piece[0]))) / 3.0
            out.append(np.array([piece[0], piece[0] + t1 * dist, piece[1] + t2 * dist, piece[1]]))
            continue
        chords = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(piece, axis=0).T))])
        u = chords / chords[-1] if chords[-1] > 0 else np.linspace(0.0, 1.0, len(piece))
        bez = _ref_generate_bezier(piece, u, t1, t2)
        dist_sq = np.sum((_ref_bezier(bez, u) - piece) ** 2, axis=1)
        if float(dist_sq.max()) < error_sq:
            out.append(bez)
            continue
        if float(dist_sq.max()) < error_sq * 4.0:
            for _ in range(20):
                u = _ref_reparameterize(piece, u, bez)
                bez = _ref_generate_bezier(piece, u, t1, t2)
                dist_sq = np.sum((_ref_bezier(bez, u) - piece) ** 2, axis=1)
                if float(dist_sq.max()) < error_sq:
                    break
            if float(dist_sq.max()) < error_sq:
                out.append(bez)
                continue
        split = int(np.argmax(dist_sq[1:-1])) + 1
        centre = _ref_normalized(piece[split - 1] - piece[split + 1])
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


# ---------------------------------------------------------------- agreement


def _same_segments(a: list[BezierSegment], b: list[BezierSegment]) -> bool:
    if len(a) != len(b):
        return False
    for sa, sb in zip(a, b):
        for pa, pb in zip(sa, sb):
            if abs(pa.x() - pb.x()) > 1e-6 or abs(pa.y() - pb.y()) > 1e-6:
                return False
    return True


def test_the_faster_simplification_keeps_the_same_points() -> None:
    strokes = [_wavy(), _circle(), _sine(2000, jitter=True), _sine(2000, quantise=True)]
    strokes += [_random_walk(seed, 400) for seed in range(12)]
    strokes.append([QPointF(0, 0), QPointF(50, 0), QPointF(100, 0)])
    strokes.append([QPointF(5, 5)] * 40)  # a zero-length chord
    for stroke in strokes:
        for tolerance in (0.5, 1.5, 2.5, 5.0):
            assert simplify_rdp(stroke, tolerance) == _ref_simplify_rdp(stroke, tolerance)


def test_the_faster_fit_gives_the_same_segments_on_the_pipeline_strokes() -> None:
    cases = [
        (_wavy(), 0.5, 0.5),
        (_wavy(), 1.5, 0.9),
        (_wavy(), 5.0, 3.0),
        (_circle(), 2.5, 1.5),
        ([QPointF(0, 0), QPointF(50, 0), QPointF(100, 0)], 0.5, 0.5),
        ([QPointF(i, (i * i) % 7) for i in range(5000)], 0.5, 0.5),
        (_sine(5000), 2.5, 1.5),
        (_sine(5000, jitter=True), 2.5, 1.5),
        (_sine(5000, quantise=True), 5.0, 3.0),
    ]
    cases += [(_random_walk(seed, 300), 1.0, 0.8) for seed in range(6)]
    for stroke, tolerance, error in cases:
        simplified = simplify_rdp(stroke, tolerance)
        assert _same_segments(
            fit_cubic_beziers(simplified, error), _ref_fit_cubic_beziers(simplified, error)
        )
    assert fit_cubic_beziers([], 1.0) == []
    one = fit_cubic_beziers([QPointF(3, 4)], 1.0)
    assert len(one) == 1 and one[0][0] == QPointF(3, 4)


# ---------------------------------------------------------------- the cost


def _fit_ms(points: list[QPointF], smoothing: float) -> float:
    item = FreehandItem()
    for p in points:
        item.add_point(p)
    start = time.perf_counter()
    item.smooth(smoothing)
    assert item.bezier_segments
    return (time.perf_counter() - start) * 1000.0


def test_the_fit_of_5000_smooth_points_is_inside_the_budget(qapp: QApplication) -> None:
    stroke = _sine(5000)
    for smoothing in (0.0, 0.5, 1.0):
        ms = min(_fit_ms(stroke, smoothing) for _ in range(2))
        assert ms < FIT_CEILING_MS, f"{ms:.1f} ms at {smoothing:.0%} smoothing"


def test_the_fit_of_5000_jittery_points_is_inside_the_budget_at_the_default_and_above(
    qapp: QApplication,
) -> None:
    for stroke in (_sine(5000, jitter=True), _sine(5000, quantise=True)):
        for smoothing in (0.5, 1.0):
            ms = min(_fit_ms(stroke, smoothing) for _ in range(2))
            assert ms < FIT_CEILING_MS, f"{ms:.1f} ms at {smoothing:.0%} smoothing"
