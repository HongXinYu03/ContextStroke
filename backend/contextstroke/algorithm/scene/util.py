"""Shared helpers for scene manifests and image compositing."""

from __future__ import annotations

from dataclasses import replace
import math
import re

from PIL import Image

from .model import Layer


def next_depth(layers: list[dict]) -> int:
    if not layers:
        return 1
    return max(int(item["depth"]) for item in layers) + 1


def display_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip() or "图层"
    return cleaned[:40]


def unique_token(used: set[str], seed: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "", seed).strip(".-_")[:32] or "layer"
    candidate = base
    number = 2
    while candidate in used:
        suffix = f"-{number}"
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        number += 1
    return candidate


def file_unused(layers: list[dict], filename: str) -> bool:
    return all(str(item.get("file")) != filename for item in layers)


def read_scale(item: dict) -> float:
    try:
        scale = float(item.get("scale", 1.0))
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(scale) or scale <= 0:
        return 1.0
    return scale


def pin_background_layers(layers: list[Layer]) -> list[Layer]:
    backgrounds = [layer for layer in layers if layer.background]
    if not backgrounds:
        return layers
    keep = backgrounds[0]
    others = [layer for layer in layers if layer.id != keep.id]
    max_other = max((layer.depth for layer in others), default=0)
    pinned = []
    for layer in layers:
        if layer.id == keep.id:
            pinned.append(replace(layer, background=True, depth=max_other + 1))
        else:
            pinned.append(replace(layer, background=False))
    return pinned


def pin_background_manifest(data: dict) -> None:
    layers = data["layers"]
    backgrounds = [item for item in layers if bool(item.get("background"))]
    if not backgrounds:
        return
    keep = backgrounds[0]
    for item in layers:
        item["background"] = str(item["id"]) == str(keep["id"])
        item["scale"] = read_scale(item)
    others = [item for item in layers if str(item["id"]) != str(keep["id"])]
    max_other = max((int(item["depth"]) for item in others), default=0)
    keep["depth"] = max_other + 1


def composite_at(base: Image.Image, sprite: Image.Image, x: int, y: int) -> None:
    sprite = sprite.convert("RGBA")
    if x < 0 or y < 0:
        sprite = sprite.crop((max(-x, 0), max(-y, 0), sprite.width, sprite.height))
        x = max(x, 0)
        y = max(y, 0)
    max_width = base.width - x
    max_height = base.height - y
    if max_width <= 0 or max_height <= 0:
        return
    sprite = sprite.crop((0, 0, min(sprite.width, max_width), min(sprite.height, max_height)))
    if sprite.width == 0 or sprite.height == 0:
        return
    region = base.crop((x, y, x + sprite.width, y + sprite.height))
    region.alpha_composite(sprite)
    base.paste(region, (x, y))


def unique_scene_id(root, seed: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "", seed).strip(".-_")[:32] or "scene"
    if not base[0].isalnum():
        base = f"s-{base}"
    candidate = base
    number = 2
    while (root / candidate).exists():
        suffix = f"-{number}"
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        number += 1
    return candidate


def safe_download_stem(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name).strip("._") or "scene"
    return cleaned[:40]
