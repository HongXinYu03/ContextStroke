"""Stroke polyline densification."""

from __future__ import annotations

import math


def resample_2d(points, spacing: float, maximum: int) -> list[tuple[float, float]] | None:
    """Keep every drawn vertex and insert points so gaps stay within spacing."""
    cleaned: list[tuple[float, float]] = []
    for point in points:
        x, y = float(point[0]), float(point[1])
        if cleaned and math.hypot(x - cleaned[-1][0], y - cleaned[-1][1]) <= 1e-6:
            continue
        cleaned.append((x, y))
    if len(cleaned) < 2:
        return None
    lengths = [
        math.hypot(end[0] - start[0], end[1] - start[1]) for start, end in zip(cleaned, cleaned[1:])
    ]
    if sum(lengths) <= 1e-6:
        return None
    gap = max(spacing, 1e-3)
    while True:
        inserts = sum(max(0, math.ceil(length / gap) - 1) for length in lengths)
        if len(cleaned) + inserts <= maximum or gap >= 32:
            break
        gap *= 2
    result = [cleaned[0]]
    for start, end, length in zip(cleaned, cleaned[1:], lengths):
        steps = max(1, math.ceil(length / gap))
        for step in range(1, steps + 1):
            t = step / steps
            result.append((start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t))
    return result
