"""Import and export scene zip archives."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import shutil
import tempfile
import zipfile

from PIL import Image

from . import paths
from .edit import sync_depths
from .store import load_manifest, save_manifest, scene_manifest
from .util import (
    display_name,
    pin_background_manifest,
    read_scale,
    safe_download_stem,
    unique_scene_id,
    unique_token,
)


def export_scene_zip(
    scene_id: str,
    *,
    depths: dict[str, int] | None = None,
    root: Path | None = None,
) -> tuple[Path, str]:
    """Pack the scene into a zip. Returns (zip_path, download_name)."""
    if depths:
        sync_depths(scene_id, depths, root)
    folder, data = load_manifest(scene_id, root)
    payload = {
        "format": paths.SCENE_FORMAT,
        "id": scene_id,
        "name": str(data.get("name") or scene_id),
        "width": int(data["width"]),
        "height": int(data["height"]),
        "layers": [],
    }
    files: list[tuple[str, Path]] = []
    for item in data["layers"]:
        filename = str(item["file"])
        if not paths.SAFE_NAME.fullmatch(filename):
            raise ValueError(f"图层文件名不安全：{filename}")
        path = folder / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        payload["layers"].append(
            {
                "id": str(item["id"]),
                "name": str(item["name"]),
                "file": filename,
                "x": int(item.get("x", 0)),
                "y": int(item.get("y", 0)),
                "depth": int(item["depth"]),
                "scale": read_scale(item),
                "background": bool(item.get("background")),
            }
        )
        files.append((filename, path))

    temp = Path(tempfile.mkdtemp(prefix="contextstroke-export-"))
    zip_path = temp / f"{scene_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(payload, ensure_ascii=False, indent=2))
        for filename, path in files:
            archive.write(path, arcname=filename)
    download_name = f"{safe_download_stem(str(data.get('name') or scene_id))}.zip"
    return zip_path, download_name


def import_scene_zip(
    zip_bytes: bytes,
    *,
    name: str | None = None,
    root: Path | None = None,
) -> dict:
    """Create a new scene from an exported zip."""
    if len(zip_bytes) > paths.MAX_IMPORT_BYTES:
        raise ValueError("导入文件不能超过 64MB")
    root = paths.scenes_root() if root is None else root
    root.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as error:
        raise ValueError("无法读取这个 zip 文件") from error

    with archive:
        names = archive.namelist()
        manifest_name = next((item for item in names if Path(item).name == "manifest.json"), None)
        if manifest_name is None:
            raise ValueError("压缩包里缺少 manifest.json")
        try:
            raw = json.loads(archive.read(manifest_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("场景清单无法读取") from error
        if not isinstance(raw, dict) or not isinstance(raw.get("layers"), list):
            raise ValueError("场景清单无法读取")
        if raw.get("format") not in {None, paths.SCENE_FORMAT}:
            raise ValueError("不支持的场景格式")
        try:
            width = int(raw["width"])
            height = int(raw["height"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("场景尺寸无效") from error
        if width < 1 or height < 1 or width > 8192 or height > 8192:
            raise ValueError("场景尺寸无效")

        members = {Path(entry).name: entry for entry in names if not entry.endswith("/")}
        layers_payload = []
        used_ids: set[str] = set()
        used_files: set[str] = set()
        for item in raw["layers"]:
            if not isinstance(item, dict):
                raise ValueError("场景清单无法读取")
            source_name = Path(str(item.get("file") or "")).name
            if source_name not in members:
                raise ValueError(f"缺少图层文件：{source_name or '未知'}")
            layer_id = unique_token(used_ids, str(item.get("id") or item.get("name") or "layer"))
            used_ids.add(layer_id)
            filename = source_name if source_name not in used_files else f"{layer_id}.png"
            if not paths.SAFE_NAME.fullmatch(filename) or not filename.lower().endswith(".png"):
                raise ValueError(f"图层文件名不安全：{filename}")
            used_files.add(filename)
            depth = int(item.get("depth", 1))
            if depth < 1:
                raise ValueError("深度必须是正整数")
            layers_payload.append(
                {
                    "id": layer_id,
                    "name": display_name(str(item.get("name") or layer_id)),
                    "file": filename,
                    "x": int(item.get("x", 0)),
                    "y": int(item.get("y", 0)),
                    "depth": depth,
                    "scale": read_scale(item),
                    "background": bool(item.get("background")),
                    "member": members[source_name],
                }
            )

        scene_label = display_name(name or str(raw.get("name") or "导入场景"))
        scene_id = unique_scene_id(root, scene_label)
        folder = root / scene_id
        folder.mkdir(parents=True, exist_ok=False)
        try:
            stored_layers = []
            for item in layers_payload:
                member = item.pop("member")
                target = folder / str(item["file"])
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                try:
                    image = Image.open(target)
                    image.verify()
                except Exception as error:
                    raise ValueError(f"图层不是有效 PNG：{item['file']}") from error
                stored_layers.append(item)
            manifest = {
                "id": scene_id,
                "name": scene_label,
                "format": paths.SCENE_FORMAT,
                "width": width,
                "height": height,
                "layers": stored_layers,
            }
            pin_background_manifest(manifest)
            save_manifest(folder, manifest)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return scene_manifest(scene_id, root)
