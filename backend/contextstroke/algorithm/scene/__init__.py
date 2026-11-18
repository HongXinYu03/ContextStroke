"""Scene manifests and alpha masks.

A scene is a stack of transparent images that share one canvas. Depth 1 is the
nearest plane. Several subjects may share a depth and then stay coplanar.
"""

from __future__ import annotations

from .blocks import ensure_blocks_scene
from .edit import add_layer, delete_layer, merge_layers, sync_depths, update_layer
from .exchange import export_scene_zip, import_scene_zip
from .model import Layer, Scene
from .paths import scenes_root
from .store import apply_depths, layer_file, list_scenes, load_scene, scene_manifest

__all__ = [
    "Layer",
    "Scene",
    "add_layer",
    "apply_depths",
    "delete_layer",
    "ensure_blocks_scene",
    "export_scene_zip",
    "import_scene_zip",
    "layer_file",
    "list_scenes",
    "load_scene",
    "merge_layers",
    "scene_manifest",
    "scenes_root",
    "sync_depths",
    "update_layer",
]
