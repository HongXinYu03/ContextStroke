"""Mask sampling and on/off boundary refinement."""

from __future__ import annotations

import numpy as np

from .scene import Scene
from .types import Hit, Sample

ALPHA = 128


def subject_layers(scene: Scene):
    return [layer for layer in scene.layers if not layer.background]


def overlapping_subjects(scene: Scene) -> set[frozenset[str]]:
    """Subject pairs whose opaque pixels meet. Disjoint layers stay a real gap."""
    step = 4
    occupants: dict[tuple[int, int], set[str]] = {}
    for layer in subject_layers(scene):
        if layer.mask.size == 0:
            continue
        sampled = layer.mask[::step, ::step] >= ALPHA
        local_ys, local_xs = np.nonzero(sampled)
        if local_ys.size == 0:
            continue
        scale = layer.scale if layer.scale > 1e-9 else 1.0
        scene_x = layer.x + local_xs.astype(np.float64) * step * scale
        scene_y = layer.y + local_ys.astype(np.float64) * step * scale
        cell_x = np.floor(scene_x / step).astype(np.int64)
        cell_y = np.floor(scene_y / step).astype(np.int64)
        for key in zip(cell_x.tolist(), cell_y.tolist()):
            occupants.setdefault((int(key[0]), int(key[1])), set()).add(layer.id)
    pairs: set[frozenset[str]] = set()
    for ids in occupants.values():
        if len(ids) < 2:
            continue
        ordered = sorted(ids)
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                pairs.add(frozenset((left, right)))
    return pairs


def local_xy(layer, x: float, y: float) -> tuple[int, int]:
    scale = layer.scale if layer.scale > 1e-9 else 1.0
    return int(round((x - layer.x) / scale)), int(round((y - layer.y) / scale))


def opaque(scene: Scene, x: float, y: float) -> bool:
    for layer in subject_layers(scene):
        lx, ly = local_xy(layer, x, y)
        height, width = layer.mask.shape
        if 0 <= lx < width and 0 <= ly < height and int(layer.mask[ly, lx]) >= ALPHA:
            return True
    return False


def sample_point(scene: Scene, x: float, y: float) -> Sample:
    hits: list[Hit] = []
    for layer in subject_layers(scene):
        lx, ly = local_xy(layer, x, y)
        height, width = layer.mask.shape
        if 0 <= lx < width and 0 <= ly < height and int(layer.mask[ly, lx]) >= ALPHA:
            hits.append(Hit(layer.id, layer.name, layer.depth))
    hits.sort(key=lambda hit: (hit.depth, hit.id))
    return Sample(x, y, bool(hits), hits)


def refine_boundaries(scene: Scene, samples: list[Sample]) -> list[Sample]:
    """Split an on/off pair on the mask silhouette instead of at the next sample."""
    if len(samples) < 2:
        return samples
    refined = [samples[0]]
    for right in samples[1:]:
        left = refined[-1]
        if left.on == right.on:
            append_distinct(refined, right)
            continue
        leaving, entering = boundary_pair(scene, left, right)
        append_distinct(refined, leaving)
        append_distinct(refined, entering)
        append_distinct(refined, right)
    return refined


def append_distinct(samples: list[Sample], sample: Sample) -> None:
    previous = samples[-1]
    if (
        abs(previous.x - sample.x) <= 1e-3
        and abs(previous.y - sample.y) <= 1e-3
        and previous.on == sample.on
    ):
        return
    samples.append(sample)


def boundary_pair(scene: Scene, left: Sample, right: Sample) -> tuple[Sample, Sample]:
    lo = 0.0
    hi = 1.0
    for _ in range(18):
        mid = (lo + hi) / 2
        x = left.x + (right.x - left.x) * mid
        y = left.y + (right.y - left.y) * mid
        if opaque(scene, x, y) == left.on:
            lo = mid
        else:
            hi = mid

    def at(t: float) -> Sample:
        return sample_point(
            scene,
            left.x + (right.x - left.x) * t,
            left.y + (right.y - left.y) * t,
        )

    leaving = at(lo)
    entering = at(hi)
    if leaving.on != left.on:
        leaving = Sample(leaving.x, leaving.y, left.on, list(left.hits))
    if entering.on == left.on:
        entering = Sample(entering.x, entering.y, right.on, list(right.hits))
    return leaving, entering
