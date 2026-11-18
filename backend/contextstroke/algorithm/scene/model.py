"""In-memory scene and layer records."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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


@dataclass
class Scene:
    id: str
    name: str
    width: int
    height: int
    layers: list[Layer]
