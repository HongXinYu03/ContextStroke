"""Classify a 2D stroke against a stack of layer masks.

A sample is on only when it hits a subject mask. The background layer is
visual only for hits: a point that touches nothing but the background stays
off. While the stroke stays on, a change in the hit-set (which subjects are
touched) starts a new atomic span. Each span keeps one depth band from its
own hits. Contiguous atomic spans (no off between them) may only change by
one depth band; off may still bridge any jump. Candidates also include the
coarser on/off spans that keep one band for a whole on-region.
"""

from __future__ import annotations

from .candidates import build_tracks
from .resample import resample_2d
from .sampling import background_front, refine_boundaries, sample_point
from .scene import Scene
from .spans import coarse_runs, fine_runs, on_off_sequences
from .types import Sample

MESSAGES = {
    "ok": "",
    "all_off": "笔触没有经过任何主体。",
    "discontinuous": "笔触在深度上不连续，已在跳变处断开。",
    "insufficient_input": "笔触至少需要两个不同的点。",
}


def solve(
    scene: Scene,
    stroke: list[tuple[float, float]] | list[list[float]],
    *,
    spacing: float = 2.0,
    maximum: int = 4000,
    max_tracks: int = 32,
) -> dict:
    resampled = resample_2d(stroke, spacing, maximum)
    if resampled is None:
        return empty_result("insufficient_input")

    samples = refine_boundaries(scene, [sample_point(scene, x, y) for x, y in resampled])
    payload = {
        "samples": [sample_payload(sample) for sample in samples],
        "sequences": on_off_sequences(samples),
        "discontinuities": [],
        "tracks": [],
    }
    atomic = fine_runs(samples)
    if not atomic:
        return {**payload, **status("all_off")}

    off_depth = background_front(scene)
    tracks = build_tracks(samples, atomic, coarse_runs(samples), max_tracks, off_depth)
    payload["tracks"] = tracks
    return {**payload, **status("ok")}


def sample_payload(sample: Sample) -> dict:
    return {
        "x": round(sample.x, 2),
        "y": round(sample.y, 2),
        "on": sample.on,
        "hits": [{"id": hit.id, "name": hit.name, "depth": hit.depth} for hit in sample.hits],
    }


def status(code: str) -> dict:
    return {"status": code, "message": MESSAGES[code]}


def empty_result(code: str) -> dict:
    return {
        **status(code),
        "samples": [],
        "sequences": [],
        "discontinuities": [],
        "tracks": [],
    }
