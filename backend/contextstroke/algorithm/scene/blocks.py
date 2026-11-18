"""Built-in color-block demo scene."""

from __future__ import annotations

from pathlib import Path
import json

from PIL import Image, ImageDraw

from . import paths

CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
BLOCKS_GENERATOR = "blocks-v1"

# Full-canvas fixture. Rects are (x, y, width, height) in canvas pixels.
BLOCK_LAYERS = (
    {
        "id": "plant",
        "name": "前景植物",
        "depth": 1,
        "file": "plant.png",
        "rect": (480, 70, 240, 280),
        "color": (68, 160, 84, 255),
    },
    {
        "id": "table",
        "name": "白色矮桌",
        "depth": 2,
        "file": "table.png",
        "rect": (220, 240, 360, 200),
        "color": (236, 236, 232, 255),
    },
    {
        "id": "slippers",
        "name": "紫色拖鞋",
        "depth": 2,
        "file": "slippers.png",
        "rect": (60, 430, 140, 110),
        "color": (142, 78, 184, 255),
    },
    {
        "id": "picture",
        "name": "背景画",
        "depth": 3,
        "file": "picture.png",
        "rect": (40, 30, 180, 140),
        "color": (78, 132, 198, 255),
    },
)


def ensure_blocks_scene(root: Path | None = None) -> Path:
    """Create the color-block scene only when it has no manifest yet.

    Adding, deleting, or merging layers rewrites that manifest. A later restart
    must keep those edits instead of restoring the original four blocks.
    """
    root = paths.scenes_root() if root is None else root
    folder = root / "blocks"
    manifest_path = folder / "manifest.json"
    if _blocks_ready(folder, manifest_path):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    for spec in BLOCK_LAYERS:
        image = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        x, y, width, height = spec["rect"]
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill=spec["color"])
        image.save(folder / spec["file"])
    manifest = {
        "id": "blocks",
        "name": "色块场景",
        "generator": BLOCKS_GENERATOR,
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "layers": [
            {
                "id": spec["id"],
                "name": spec["name"],
                "file": spec["file"],
                "x": 0,
                "y": 0,
                "depth": spec["depth"],
            }
            for spec in BLOCK_LAYERS
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def _blocks_ready(folder: Path, manifest_path: Path) -> bool:
    if not manifest_path.is_file():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and isinstance(data.get("layers"), list)
