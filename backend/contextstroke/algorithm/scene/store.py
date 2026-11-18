"""Load and list scene manifests from disk."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json

import numpy as np
from PIL import Image

from . import paths
from .blocks import ensure_blocks_scene
from .model import Layer, Scene
from .util import pin_background_layers, read_scale


def list_scenes(root: Path | None = None) -> list[dict[str, str]]:
    root = ensure_blocks_scene(root).parent
    scenes = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes.append({"id": folder.name, "name": str(data.get("name") or folder.name)})
    return scenes


def load_scene(scene_id: str, root: Path | None = None) -> Scene:
    root = paths.scenes_root() if root is None else root
    ensure_blocks_scene(root)
    if not paths.SAFE_NAME.fullmatch(scene_id):
        raise FileNotFoundError(scene_id)
    folder = root / scene_id
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(scene_id)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    width = int(data["width"])
    height = int(data["height"])
    layers: list[Layer] = []
    for item in data["layers"]:
        filename = str(item["file"])
        if not paths.SAFE_NAME.fullmatch(filename):
            raise ValueError(f"图层文件名不安全：{filename}")
        path = folder / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        image = Image.open(path).convert("RGBA")
        alpha = np.asarray(image)[:, :, 3]
        layers.append(
            Layer(
                id=str(item["id"]),
                name=str(item["name"]),
                depth=int(item["depth"]),
                x=int(item["x"]),
                y=int(item["y"]),
                file=filename,
                mask=alpha,
                scale=read_scale(item),
                background=bool(item.get("background")),
            )
        )
    layers = pin_background_layers(layers)
    return Scene(id=scene_id, name=str(data.get("name") or scene_id), width=width, height=height, layers=layers)


def scene_manifest(scene_id: str, root: Path | None = None) -> dict:
    scene = load_scene(scene_id, root)
    return {
        "id": scene.id,
        "name": scene.name,
        "width": scene.width,
        "height": scene.height,
        "layers": [
            {
                "id": layer.id,
                "name": layer.name,
                "file": layer.file,
                "x": layer.x,
                "y": layer.y,
                "depth": layer.depth,
                "scale": layer.scale,
                "background": layer.background,
                "pixel_width": int(layer.mask.shape[1]),
                "pixel_height": int(layer.mask.shape[0]),
                "display_width": int(round(layer.mask.shape[1] * layer.scale)),
                "display_height": int(round(layer.mask.shape[0] * layer.scale)),
                "image_url": f"/api/scenes/{scene.id}/files/{layer.file}",
            }
            for layer in scene.layers
        ],
    }


def apply_depths(scene: Scene, depths: dict[str, int] | None) -> Scene:
    if not depths:
        return replace(scene, layers=pin_background_layers(scene.layers))
    layers = []
    for layer in scene.layers:
        depth = int(depths[layer.id]) if layer.id in depths else layer.depth
        if depth < 1:
            raise ValueError(f"{layer.name} 的深度必须是正整数")
        layers.append(replace(layer, depth=depth))
    return replace(scene, layers=pin_background_layers(layers))


def load_manifest(scene_id: str, root: Path | None) -> tuple[Path, dict]:
    root = paths.scenes_root() if root is None else root
    ensure_blocks_scene(root)
    if not paths.SAFE_NAME.fullmatch(scene_id):
        raise FileNotFoundError(scene_id)
    folder = root / scene_id
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(scene_id)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("layers"), list):
        raise ValueError("场景清单无法读取")
    return folder, data


def save_manifest(folder: Path, data: dict) -> None:
    (folder / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def layer_file(scene_id: str, filename: str, root: Path | None = None) -> Path:
    root = paths.scenes_root() if root is None else root
    if not paths.SAFE_NAME.fullmatch(scene_id) or not paths.SAFE_NAME.fullmatch(filename):
        raise FileNotFoundError(filename)
    path = (root / scene_id / filename).resolve()
    if path.parent != (root / scene_id).resolve() or not path.is_file():
        raise FileNotFoundError(filename)
    return path
