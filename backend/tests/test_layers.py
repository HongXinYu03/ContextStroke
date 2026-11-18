import base64
import json
import shutil
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from contextstroke.algorithm import scene as scene_module
from contextstroke.algorithm.scene import (
    add_layer,
    delete_layer,
    ensure_blocks_scene,
    export_scene_zip,
    import_scene_zip,
    load_scene,
    merge_layers,
    update_layer,
)
from contextstroke.algorithm.solve import solve
from contextstroke.server.api import app


def _workspace() -> Path:
    root = Path(__file__).resolve().parent / "_workspace"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    return root


def _png(width, height, color) -> bytes:
    image = Image.new("RGBA", (width, height), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_existing_manifest_is_not_rewritten():
    tmp_path = _workspace()
    folder = ensure_blocks_scene(tmp_path)
    manifest_path = folder / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["layers"] = data["layers"][:1]
    data["name"] = "改过的场景"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    (folder / "table.png").unlink()

    ensure_blocks_scene(tmp_path)

    kept = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert kept["name"] == "改过的场景"
    assert [item["id"] for item in kept["layers"]] == ["plant"]
    assert not (folder / "table.png").exists()


def test_add_delete_and_merge_layers():
    tmp_path = _workspace()
    ensure_blocks_scene(tmp_path)
    added = add_layer( "blocks", _png(30, 20, (255, 0, 0, 255)), "新物件.png", root=tmp_path)
    created = next(layer for layer in added["layers"] if layer["name"] == "新物件")
    assert created["depth"] == 4
    assert created["pixel_width"] == 30

    removed = delete_layer("blocks", "slippers", root=tmp_path)
    assert {layer["id"] for layer in removed["layers"]} == {"plant", "table", "picture", created["id"]}
    assert not (tmp_path / "blocks" / "slippers.png").exists()

    merged = merge_layers("blocks", "plant", "picture", depth=1, root=tmp_path)
    ids = {layer["id"] for layer in merged["layers"]}
    assert "plant" not in ids
    assert "picture" not in ids
    result = next(layer for layer in merged["layers"] if layer["id"] not in {"table", created["id"]})
    assert result["depth"] == 1
    assert result["name"] == "前景植物与背景画"
    mask = Image.open(tmp_path / "blocks" / result["file"]).convert("RGBA")
    assert mask.getpixel((500, 100))[3] == 255
    assert mask.getpixel((80, 60))[3] == 255
    assert mask.getpixel((300, 300))[3] == 0
    assert not (tmp_path / "blocks" / "plant.png").exists()
    assert not (tmp_path / "blocks" / "picture.png").exists()

    ensure_blocks_scene(tmp_path)
    assert {layer["id"] for layer in merged["layers"]} == {
        layer["id"] for layer in json.loads((tmp_path / "blocks" / "manifest.json").read_text(encoding="utf-8"))["layers"]
    }


def test_update_transform_and_background():
    tmp_path = _workspace()
    ensure_blocks_scene(tmp_path)
    add_layer("blocks", _png(100, 80, (10, 10, 10, 255)), "bg.png", root=tmp_path)
    moved = update_layer("blocks", "plant", x=10, y=20, scale=0.5, root=tmp_path)
    plant = next(layer for layer in moved["layers"] if layer["id"] == "plant")
    assert plant["x"] == 10
    assert plant["y"] == 20
    assert plant["scale"] == 0.5
    assert plant["display_width"] == 400

    bg_id = next(layer["id"] for layer in moved["layers"] if layer["name"] == "bg")
    backed = update_layer("blocks", bg_id, background=True, root=tmp_path)
    background = next(layer for layer in backed["layers"] if layer["id"] == bg_id)
    assert background["background"] is True
    assert background["depth"] == max(layer["depth"] for layer in backed["layers"])
    assert sum(1 for layer in backed["layers"] if layer["background"]) == 1

    scene = load_scene("blocks", tmp_path)
    only_background = solve(scene, [(20, 20), (80, 20)])
    assert only_background["status"] == "all_off"
    assert only_background["tracks"] == []
    assert all(not sample["on"] for sample in only_background["samples"])

    crossing = solve(scene, [(20, 20), (500, 120)])
    assert crossing["status"] == "ok"
    assert any(sample["on"] for sample in crossing["samples"])
    assert any(not sample["on"] for sample in crossing["samples"])
    assert "空白" in crossing["tracks"][0]["summary"]


def test_export_and_import_preserve_depth_layout():
    tmp_path = _workspace()
    ensure_blocks_scene(tmp_path)
    update_layer("blocks", "plant", x=12, y=34, scale=0.5, root=tmp_path)
    zip_path, download_name = export_scene_zip(
        "blocks",
        depths={"plant": 3, "table": 1, "slippers": 1, "picture": 2},
        root=tmp_path,
    )
    assert download_name.endswith(".zip")
    payload = zip_path.read_bytes()
    shutil.rmtree(zip_path.parent)

    imported = import_scene_zip(payload, name="分享场景", root=tmp_path)
    assert imported["name"] == "分享场景"
    assert imported["id"] != "blocks"
    by_id = {layer["id"]: layer for layer in imported["layers"]}
    assert by_id["plant"]["depth"] == 3
    assert by_id["plant"]["x"] == 12
    assert by_id["plant"]["y"] == 34
    assert by_id["plant"]["scale"] == 0.5
    assert by_id["table"]["depth"] == 1
    assert (tmp_path / imported["id"] / "plant.png").is_file()


def test_layer_routes_do_not_touch_the_workspace_scene(monkeypatch):
    tmp_path = _workspace()
    monkeypatch.setattr(scene_module.paths, "scenes_root", lambda: tmp_path)
    ensure_blocks_scene(tmp_path)
    client = TestClient(app)
    encoded = base64.b64encode(_png(16, 16, (0, 0, 0, 255))).decode("ascii")

    added = client.post(
        "/api/scenes/blocks/layers",
        json={"name": "标记.png", "image_base64": encoded, "depth": 5},
    )
    assert added.status_code == 200
    created = next(layer for layer in added.json()["layers"] if layer["name"] == "标记")
    assert created["depth"] == 5

    merged = client.post(
        "/api/scenes/blocks/layers/merge",
        json={"ids": ["table", "slippers"], "depth": 2},
    )
    assert merged.status_code == 200
    assert {layer["id"] for layer in merged.json()["layers"]} >= {"plant", "picture"}
    assert "table" not in {layer["id"] for layer in merged.json()["layers"]}

    deleted = client.delete(f"/api/scenes/blocks/layers/{created['id']}")
    assert deleted.status_code == 200
    assert created["id"] not in {layer["id"] for layer in deleted.json()["layers"]}
