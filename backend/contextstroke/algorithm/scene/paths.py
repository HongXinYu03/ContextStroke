"""Scene directory helpers."""

from __future__ import annotations

from pathlib import Path
import re

SAFE_NAME = re.compile(r"[A-Za-z0-9._-]+")
SCENE_FORMAT = "contextstroke-scene-v1"
MAX_IMPORT_BYTES = 64 * 1024 * 1024


def scenes_root() -> Path:
    # algorithm/scene/paths.py -> backend/scenes
    return Path(__file__).resolve().parents[3] / "scenes"
