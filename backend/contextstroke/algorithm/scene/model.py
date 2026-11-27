"""In-memory scene and layer records."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class InstanceNote:
    """User annotation for one object instance inside a layer.

    ``seed`` is a layer-local pixel inside the instance. Instances are detected
    on demand, so the seed is what ties the note back to its object.
    """

    seed: tuple[int, int]
    category: str | None = None
    metric_width: float | None = None
    metric_height: float | None = None


@dataclass
class Layer:
    id: str
    name: str
    depth: int
    x: int
    y: int
    file: str
    mask: np.ndarray
    scale: float = 1.0
    background: bool = False
    instances: tuple[InstanceNote, ...] = ()


@dataclass
class Scene:
    id: str
    name: str
    width: int
    height: int
    layers: list[Layer]
    meters_per_pixel: float | None = None
