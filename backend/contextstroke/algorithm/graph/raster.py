"""Instance footprints on the shared scene canvas."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..scene.model import Layer
from .instances import Instance

CELL = 4  # canvas pixels per occupancy cell
_KEY = 1 << 24  # packs (cell_y, cell_x) into one int64; offset keeps it non-negative


@dataclass(frozen=True)
class Footprint:
    bbox: tuple[float, float, float, float]  # canvas px: x0, y0, x1, y1
    centroid: tuple[float, float]  # canvas px
    cells: np.ndarray  # sorted unique int64 keys of occupied CELL x CELL cells


def layer_scale(layer: Layer) -> float:
    return layer.scale if layer.scale > 1e-9 else 1.0


def footprint(layer: Layer, instance: Instance) -> Footprint:
    scale = layer_scale(layer)
    x0, y0, x1, y1 = instance.bbox_local
    bbox = (
        layer.x + x0 * scale,
        layer.y + y0 * scale,
        layer.x + x1 * scale,
        layer.y + y1 * scale,
    )
    cx, cy = instance.centroid_local
    centroid = (layer.x + cx * scale, layer.y + cy * scale)
    stride = max(1, int(math.floor(CELL / scale)))
    sampled = instance.mask[::stride, ::stride]
    local_ys, local_xs = np.nonzero(sampled)
    canvas_x = layer.x + (local_xs.astype(np.float64) * stride + 0.5) * scale
    canvas_y = layer.y + (local_ys.astype(np.float64) * stride + 0.5) * scale
    cell_x = np.floor(canvas_x / CELL).astype(np.int64) + _KEY // 2
    cell_y = np.floor(canvas_y / CELL).astype(np.int64) + _KEY // 2
    cells = np.unique(cell_y * _KEY + cell_x)
    return Footprint(bbox=bbox, centroid=centroid, cells=cells)


def overlap_cells(left: Footprint, right: Footprint) -> int:
    if left.cells.size == 0 or right.cells.size == 0:
        return 0
    return int(np.intersect1d(left.cells, right.cells, assume_unique=True).size)
