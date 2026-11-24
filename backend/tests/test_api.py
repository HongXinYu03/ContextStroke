import io
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from contextstroke.algorithm import scene as scene_module
from contextstroke.algorithm.scene import ensure_blocks_scene
from contextstroke.server.api import app


def _workspace() -> Path:
    root = Path(__file__).resolve().parent / "_workspace_api"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    return root


def test_blocks_scene_and_cross_layer_stroke(monkeypatch):
    tmp_path = _workspace()
    monkeypatch.setattr(scene_module.paths, "scenes_root", lambda: tmp_path)
    ensure_blocks_scene(tmp_path)
    client = TestClient(app)

    scenes = client.get("/api/scenes")
    assert scenes.status_code == 200
    assert any(item["id"] == "blocks" for item in scenes.json())

    scene = client.get("/api/scenes/blocks")
    assert scene.status_code == 200
    body = scene.json()
    assert body["width"] == 800
    assert body["height"] == 600
    assert {layer["id"] for layer in body["layers"]} == {"plant", "table", "slippers", "picture"}

    image = client.get("/api/scenes/blocks/files/plant.png")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert client.get("/api/scenes/blocks/files/missing.png").status_code == 404
    assert client.get("/api/scenes/missing").status_code == 404

    solved = client.post(
        "/api/solve",
        json={
            "scene": "blocks",
            "depths": {"plant": 1, "table": 2, "slippers": 2, "picture": 3},
            "stroke": [[660, 112], [520, 300], [300, 320]],
        },
    )
    assert solved.status_code == 200
    result = solved.json()
    assert result["status"] == "ok"
    assert result["tracks"][0]["selected"] is True
    assert result["tracks"][0]["cost"] == 0
    # The plant-only span is opened by the table contour, so it stays on the table.
    # The cheapest constant reading is the band between plant and table.
    assert result["tracks"][0]["summary"] == "1-2"
    summaries = {track["summary"] for track in result["tracks"]}
    # Plant still cuts the overlap and the table span; the table pass keeps table bands.
    assert {"0-1", "1-2", "2-3"} <= {
        segment["label"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["relation"] == "band"
    }
    assert any("→" in summary for summary in summaries)

    shifted = client.post(
        "/api/solve",
        json={
            "scene": "blocks",
            "depths": {"plant": 3, "table": 1, "slippers": 1, "picture": 2},
            "stroke": [[660, 112], [520, 300], [300, 320]],
        },
    )
    assert shifted.status_code == 200
    assert {track["summary"] for track in shifted.json()["tracks"]} != {
        track["summary"] for track in result["tracks"]
    }

    exported = client.post(
        "/api/scenes/blocks/export",
        json={"depths": {"plant": 2, "table": 1, "slippers": 1, "picture": 3}},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")

    imported = client.post(
        "/api/scenes/import",
        files={"file": ("room.zip", io.BytesIO(exported.content), "application/zip")},
        data={"name": "分享客厅"},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["name"] == "分享客厅"
    assert {layer["id"]: layer["depth"] for layer in body["layers"]}["plant"] == 2
