import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contextstroke.algorithm import scene as scene_module
from contextstroke.algorithm.scene import (
    annotate_instance,
    ensure_blocks_scene,
    export_scene_zip,
    import_scene_zip,
    merge_layers,
    update_scene_meta,
)
from contextstroke.server.api import app


def _workspace() -> Path:
    root = Path(__file__).resolve().parent / "_workspace_graph"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    return root


def _manifest(root: Path, scene_id: str = "blocks") -> dict:
    return json.loads((root / scene_id / "manifest.json").read_text(encoding="utf-8"))


def test_annotate_instance_writes_clears_and_validates():
    root = _workspace()
    ensure_blocks_scene(root)
    annotate_instance("blocks", "plant:0", category="龟背竹", metric_width=0.8, root=root)
    plant = next(item for item in _manifest(root)["layers"] if item["id"] == "plant")
    assert len(plant["instances"]) == 1
    note = plant["instances"][0]
    assert note["category"] == "龟背竹"
    assert note["metric_width"] == 0.8
    seed_x, seed_y = note["seed"]
    # Plant block is (480, 70, 240, 280) in a full-canvas PNG.
    assert 480 <= seed_x < 720 and 70 <= seed_y < 350

    annotate_instance("blocks", "plant:0", metric_height=1.5, root=root)
    plant = next(item for item in _manifest(root)["layers"] if item["id"] == "plant")
    assert plant["instances"][0] == {"seed": [seed_x, seed_y], "category": "龟背竹", "metric_width": 0.8, "metric_height": 1.5}

    with pytest.raises(ValueError):
        annotate_instance("blocks", "plant:0", metric_width=-1, root=root)
    with pytest.raises(ValueError):
        annotate_instance("blocks", "plant:5", category="x", root=root)

    annotate_instance("blocks", "plant:0", category="", metric_width=None, metric_height=None, root=root)
    plant = next(item for item in _manifest(root)["layers"] if item["id"] == "plant")
    assert "instances" not in plant


def test_annotations_survive_export_import_and_drop_on_merge():
    root = _workspace()
    ensure_blocks_scene(root)
    annotate_instance("blocks", "table:0", category="矮桌", metric_width=1.2, root=root)
    update_scene_meta("blocks", meters_per_pixel=0.004, root=root)

    zip_path, _ = export_scene_zip("blocks", root=root)
    payload = zip_path.read_bytes()
    shutil.rmtree(zip_path.parent)
    imported = import_scene_zip(payload, name="分享", root=root)
    assert imported["meters_per_pixel"] == 0.004
    table = next(item for item in _manifest(root, imported["id"])["layers"] if item["id"] == "table")
    assert table["instances"][0]["category"] == "矮桌"

    merged = merge_layers("blocks", "table", "slippers", root=root)
    created = next(layer for layer in merged["layers"] if layer["id"] not in {"plant", "picture"})
    stored = next(item for item in _manifest(root)["layers"] if item["id"] == created["id"])
    assert "instances" not in stored

    cleared = update_scene_meta("blocks", meters_per_pixel=None, root=root)
    assert cleared["meters_per_pixel"] is None
    with pytest.raises(ValueError):
        update_scene_meta("blocks", meters_per_pixel=0, root=root)


def test_graph_routes(monkeypatch):
    root = _workspace()
    monkeypatch.setattr(scene_module.paths, "scenes_root", lambda: root)
    ensure_blocks_scene(root)
    client = TestClient(app)

    response = client.post("/api/scenes/blocks/graph", json={})
    assert response.status_code == 200
    graph = response.json()
    assert graph["frame"]["source"] == "canvas"
    assert [node["id"] for node in graph["nodes"]] == ["plant:0", "slippers:0", "table:0", "picture:0"]
    assert len(graph["edges"]) == 6
    plant_table = next(edge for edge in graph["edges"] if {edge["u"], edge["v"]} == {"plant:0", "table:0"})
    assert plant_table["u"] == "plant:0"
    assert plant_table["occlusion"]["occluded"] is True
    assert plant_table["occlusion"]["occluder"] == "plant:0"

    flipped = client.post("/api/scenes/blocks/graph", json={"depths": {"plant": 3, "table": 1}})
    assert flipped.status_code == 200
    edge = next(item for item in flipped.json()["edges"] if {item["u"], item["v"]} == {"plant:0", "table:0"})
    assert edge["u"] == "table:0"
    assert edge["occlusion"]["occluder"] == "table:0"

    annotated = client.patch(
        "/api/scenes/blocks/instances/plant%3A0",
        json={"category": "龟背竹", "metric_width": 0.96},
    )
    assert annotated.status_code == 200
    plant = next(node for node in annotated.json()["nodes"] if node["id"] == "plant:0")
    assert plant["category"] == "龟背竹"
    assert plant["metric"]["width_source"] == "manual"
    assert annotated.json()["meters_per_pixel_source"] == "derived"

    bad = client.patch("/api/scenes/blocks/instances/plant%3A0", json={"metric_width": 5000})
    assert bad.status_code == 400
    assert client.patch("/api/scenes/blocks/instances/nope%3A0", json={"category": "x"}).status_code == 400
    assert client.post("/api/scenes/missing/graph", json={}).status_code == 404

    meta = client.patch("/api/scenes/blocks", json={"meters_per_pixel": 0.005})
    assert meta.status_code == 200
    assert meta.json()["meters_per_pixel"] == 0.005
    regraph = client.post("/api/scenes/blocks/graph").json()
    assert regraph["meters_per_pixel_source"] == "manual"
