"""Add, update, delete, merge layers and sync depths."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import math

from PIL import Image

from . import paths
from .store import load_manifest, save_manifest, scene_manifest
from .util import (
    composite_at,
    display_name,
    file_unused,
    next_depth,
    pin_background_manifest,
    read_scale,
    unique_token,
)


def add_layer(
    scene_id: str,
    png_bytes: bytes,
    name: str,
    *,
    depth: int | None = None,
    root: Path | None = None,
) -> dict:
    """Save a PNG into the scene. Depth defaults to one past the current maximum."""
    folder, data = load_manifest(scene_id, root)
    if len(png_bytes) > 8 * 1024 * 1024:
        raise ValueError("图片不能超过 8MB")
    try:
        image = Image.open(BytesIO(png_bytes)).convert("RGBA")
    except Exception as error:
        raise ValueError("无法读取这张图片") from error
    if image.width == 0 or image.height == 0 or image.getextrema()[3][1] == 0:
        raise ValueError("图片里没有不透明的像素")
    layers = data["layers"]
    used = {str(item["id"]) for item in layers} | {Path(str(item["file"])).stem for item in layers}
    layer_id = unique_token(used, Path(name).stem)
    filename = f"{layer_id}.png"
    image.save(folder / filename)
    stored_depth = int(depth) if depth is not None else next_depth(layers)
    if stored_depth < 1:
        raise ValueError("深度必须是正整数")
    layers.append(
        {
            "id": layer_id,
            "name": display_name(Path(name).stem),
            "file": filename,
            "x": 0,
            "y": 0,
            "scale": 1.0,
            "background": False,
            "depth": stored_depth,
        }
    )
    data.pop("generator", None)
    pin_background_manifest(data)
    save_manifest(folder, data)
    return scene_manifest(scene_id, root)


def update_layer(
    scene_id: str,
    layer_id: str,
    *,
    x: int | None = None,
    y: int | None = None,
    scale: float | None = None,
    background: bool | None = None,
    root: Path | None = None,
) -> dict:
    """Move, scale, or mark a layer as the scene background."""
    folder, data = load_manifest(scene_id, root)
    target = next((item for item in data["layers"] if str(item["id"]) == layer_id), None)
    if target is None:
        raise ValueError("找不到要更新的图层")
    if x is not None:
        target["x"] = int(x)
    if y is not None:
        target["y"] = int(y)
    if scale is not None:
        if not math.isfinite(scale) or scale < 0.05 or scale > 20:
            raise ValueError("缩放必须在 0.05 到 20 之间")
        target["scale"] = round(float(scale), 4)
    if background is True:
        for item in data["layers"]:
            item["background"] = str(item["id"]) == layer_id
        target["x"] = int(target.get("x", 0)) if x is None else int(x)
        target["y"] = int(target.get("y", 0)) if y is None else int(y)
        path = folder / str(target["file"])
        image = Image.open(path)
        data["width"] = max(int(data["width"]), image.width)
        data["height"] = max(int(data["height"]), image.height)
        if x is None:
            target["x"] = 0
        if y is None:
            target["y"] = 0
        if scale is None and "scale" not in target:
            target["scale"] = 1.0
    elif background is False:
        target["background"] = False
    data.pop("generator", None)
    pin_background_manifest(data)
    save_manifest(folder, data)
    return scene_manifest(scene_id, root)


def delete_layer(scene_id: str, layer_id: str, root: Path | None = None) -> dict:
    folder, data = load_manifest(scene_id, root)
    layers = data["layers"]
    removed = [item for item in layers if str(item["id"]) == layer_id]
    if not removed:
        raise ValueError("找不到要删除的图层")
    data["layers"] = [item for item in layers if str(item["id"]) != layer_id]
    data.pop("generator", None)
    pin_background_manifest(data)
    save_manifest(folder, data)
    for item in removed:
        filename = str(item["file"])
        if file_unused(data["layers"], filename):
            target = folder / filename
            if target.is_file() and paths.SAFE_NAME.fullmatch(filename):
                target.unlink()
    return scene_manifest(scene_id, root)


def merge_layers(
    scene_id: str,
    left_id: str,
    right_id: str,
    *,
    depth: int | None = None,
    root: Path | None = None,
) -> dict:
    """Union the two alpha masks. The result keeps the nearer depth, then both sources go."""
    if left_id == right_id:
        raise ValueError("请选择两个不同的图层")
    folder, data = load_manifest(scene_id, root)
    layers = data["layers"]
    by_id = {str(item["id"]): item for item in layers}
    if left_id not in by_id or right_id not in by_id:
        raise ValueError("找不到要合并的图层")
    left = by_id[left_id]
    right = by_id[right_id]
    width = int(data["width"])
    height = int(data["height"])
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if bool(left.get("background")) or bool(right.get("background")):
        raise ValueError("背景图层不能合并")
    nearer_first = sorted((left, right), key=lambda item: int(item["depth"]), reverse=True)
    for item in nearer_first:
        sprite = Image.open(folder / str(item["file"])).convert("RGBA")
        scale = read_scale(item)
        if abs(scale - 1.0) > 1e-6:
            width_px = max(1, int(round(sprite.width * scale)))
            height_px = max(1, int(round(sprite.height * scale)))
            sprite = sprite.resize((width_px, height_px), Image.Resampling.BILINEAR)
        composite_at(canvas, sprite, int(item["x"]), int(item["y"]))
    stored_depth = int(depth) if depth is not None else min(int(left["depth"]), int(right["depth"]))
    if stored_depth < 1:
        raise ValueError("深度必须是正整数")
    used = {str(item["id"]) for item in layers} | {Path(str(item["file"])).stem for item in layers}
    layer_id = unique_token(used, "merged")
    filename = f"{layer_id}.png"
    canvas.save(folder / filename)
    data["layers"] = [item for item in layers if str(item["id"]) not in {left_id, right_id}]
    data["layers"].append(
        {
            "id": layer_id,
            "name": display_name(f"{left['name']}与{right['name']}"),
            "file": filename,
            "x": 0,
            "y": 0,
            "scale": 1.0,
            "background": False,
            "depth": stored_depth,
        }
    )
    data.pop("generator", None)
    pin_background_manifest(data)
    save_manifest(folder, data)
    for item in (left, right):
        filename_old = str(item["file"])
        if file_unused(data["layers"], filename_old) and paths.SAFE_NAME.fullmatch(filename_old):
            target = folder / filename_old
            if target.is_file():
                target.unlink()
    return scene_manifest(scene_id, root)


def sync_depths(scene_id: str, depths: dict[str, int], root: Path | None = None) -> dict:
    """Write the caller's depth order into the scene manifest."""
    folder, data = load_manifest(scene_id, root)
    known = {str(item["id"]) for item in data["layers"]}
    unknown = [layer_id for layer_id in depths if layer_id not in known]
    if unknown:
        raise ValueError(f"找不到图层：{unknown[0]}")
    for item in data["layers"]:
        layer_id = str(item["id"])
        if layer_id not in depths:
            continue
        depth = int(depths[layer_id])
        if depth < 1:
            raise ValueError(f"{item.get('name', layer_id)} 的深度必须是正整数")
        item["depth"] = depth
    data.pop("generator", None)
    pin_background_manifest(data)
    save_manifest(folder, data)
    return scene_manifest(scene_id, root)
