"""Split one layer's own alpha mask into object instances.

Only the layer's own pixels matter. Other layers drawn on top do not cut it, so
an occluded object stays one connected subject.

Steps (all in layer-local pixels, independent of the layer's x / y / scale):
1. Block-downsample by ``STEP`` (a cell is on when any pixel in it is opaque).
2. Dilate by ``GAP_PX`` so hairline cracks from matting merge into one object.
3. 8-connected labeling (run-length union-find, no scipy).
4. Drop specks smaller than ``max(MIN_AREA_PX, MIN_AREA_FRACTION * largest)``.
5. Number the rest by local bbox ``(x0, y0)``; id is ``"{layer_id}:{k}"``.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math

import numpy as np

from ..scene.model import InstanceNote, Layer

ALPHA = 128
STEP = 2
GAP_PX = 4
MIN_AREA_PX = 64
MIN_AREA_FRACTION = 0.01
_CACHE_SIZE = 64


@dataclass(frozen=True)
class Instance:
    id: str
    layer_id: str
    index: int
    mask: np.ndarray  # bool, same shape as layer.mask
    bbox_local: tuple[int, int, int, int]  # x0, y0, x1, y1 (x1 / y1 exclusive)
    centroid_local: tuple[float, float]  # pixel-center coordinates
    area: int


_cache: OrderedDict[tuple, list[tuple[np.ndarray, tuple, tuple, int]]] = OrderedDict()


def detect_instances(layer: Layer) -> list[Instance]:
    opaque = np.asarray(layer.mask) >= ALPHA
    key = (opaque.shape, hashlib.blake2b(np.packbits(opaque).tobytes(), digest_size=16).hexdigest())
    parts = _cache.get(key)
    if parts is None:
        parts = _split(opaque)
        _cache[key] = parts
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    return [
        Instance(
            id=f"{layer.id}:{index}",
            layer_id=layer.id,
            index=index,
            mask=mask,
            bbox_local=bbox,
            centroid_local=centroid,
            area=area,
        )
        for index, (mask, bbox, centroid, area) in enumerate(parts)
    ]


def _split(opaque: np.ndarray) -> list[tuple[np.ndarray, tuple, tuple, int]]:
    if opaque.size == 0 or not opaque.any():
        return []
    height, width = opaque.shape
    cells = _block_any(opaque, STEP)
    radius = max(1, math.ceil(GAP_PX / 2 / STEP))
    labels_small = _label8(_dilate(cells, radius)) * cells
    labels = np.repeat(np.repeat(labels_small, STEP, axis=0), STEP, axis=1)[:height, :width]
    labels = np.where(opaque, labels, 0)
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    if counts.max(initial=0) == 0:
        return []
    threshold = max(MIN_AREA_PX, MIN_AREA_FRACTION * int(counts.max()))
    parts = []
    for label in np.nonzero(counts >= threshold)[0]:
        mask = labels == label
        ys, xs = np.nonzero(mask)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        centroid = (float(xs.mean()) + 0.5, float(ys.mean()) + 0.5)
        parts.append((mask, bbox, centroid, int(xs.size)))
    parts.sort(key=lambda part: (part[1][0], part[1][1]))
    return parts


def _block_any(mask: np.ndarray, step: int) -> np.ndarray:
    height, width = mask.shape
    padded_h = -(-height // step) * step
    padded_w = -(-width // step) * step
    padded = np.zeros((padded_h, padded_w), dtype=bool)
    padded[:height, :width] = mask
    return padded.reshape(padded_h // step, step, padded_w // step, step).any(axis=(1, 3))


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown[1:, 1:] |= out[:-1, :-1]
        grown[1:, :-1] |= out[:-1, 1:]
        grown[:-1, 1:] |= out[1:, :-1]
        grown[:-1, :-1] |= out[1:, 1:]
        out = grown
    return out


def _label8(mask: np.ndarray) -> np.ndarray:
    """8-connected component labels (0 = empty, 1..n = components)."""
    height, width = mask.shape
    parent: list[int] = [0]

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    rows_runs: list[list[tuple[int, int, int]]] = []
    previous: list[tuple[int, int, int]] = []
    padded = np.zeros(width + 2, dtype=np.int8)
    for row in range(height):
        padded[1:-1] = mask[row]
        edges = np.diff(padded)
        starts = np.nonzero(edges == 1)[0]
        ends = np.nonzero(edges == -1)[0]
        current: list[tuple[int, int, int]] = []
        pointer = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            run_id = len(parent)
            parent.append(run_id)
            while pointer < len(previous) and previous[pointer][1] < start:
                pointer += 1
            scan = pointer
            # 8-connectivity: [start, end) touches [s, e) when s <= end and e >= start.
            while scan < len(previous) and previous[scan][0] <= end:
                if previous[scan][1] >= start:
                    left, right = find(run_id), find(previous[scan][2])
                    if left != right:
                        parent[max(left, right)] = min(left, right)
                scan += 1
            current.append((start, end, run_id))
        rows_runs.append(current)
        previous = current

    roots: dict[int, int] = {}
    labels = np.zeros((height, width), dtype=np.int32)
    for row, runs in enumerate(rows_runs):
        for start, end, run_id in runs:
            root = find(run_id)
            label = roots.setdefault(root, len(roots) + 1)
            labels[row, start:end] = label
    return labels


def seed_for(instance: Instance) -> tuple[int, int]:
    """Opaque layer-local pixel nearest to the instance centroid."""
    ys, xs = np.nonzero(instance.mask)
    cx, cy = instance.centroid_local
    index = int(np.argmin((xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2))
    return int(xs[index]), int(ys[index])


def instance_at(instances: list[Instance], seed: tuple[int, int]) -> Instance | None:
    sx, sy = seed
    for instance in instances:
        height, width = instance.mask.shape
        if 0 <= sx < width and 0 <= sy < height and bool(instance.mask[sy, sx]):
            return instance
    return None


def match_notes(
    instances: list[Instance],
    notes: tuple[InstanceNote, ...] | list[InstanceNote],
) -> tuple[dict[str, InstanceNote], list[InstanceNote]]:
    """Attach notes to instances by seed. A note whose seed misses stays unmatched."""
    matched: dict[str, InstanceNote] = {}
    unmatched: list[InstanceNote] = []
    for note in notes:
        instance = instance_at(instances, note.seed)
        if instance is None or instance.id in matched:
            unmatched.append(note)
            continue
        matched[instance.id] = note
    return matched, unmatched
