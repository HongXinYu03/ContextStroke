"""3D scene graph derived from the layered scene.

Nodes are object instances (connected parts of each layer's own mask); edges
connect every pair and carry a canonical front-to-back vector plus occlusion.
"""

from __future__ import annotations

from .build import build_scene_graph, reference_frame
from .instances import Instance, detect_instances, match_notes, seed_for
from .types import Occlusion, SceneEdge, SceneGraph, SceneNode

__all__ = [
    "Instance",
    "Occlusion",
    "SceneEdge",
    "SceneGraph",
    "SceneNode",
    "build_scene_graph",
    "detect_instances",
    "match_notes",
    "reference_frame",
    "seed_for",
]
