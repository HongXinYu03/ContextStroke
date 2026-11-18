"""HTTP API. The algorithm stays independent of FastAPI."""

from __future__ import annotations

import base64
import math
import shutil

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.background import BackgroundTask

from contextstroke.algorithm.scene import (
    add_layer,
    apply_depths,
    delete_layer,
    export_scene_zip,
    import_scene_zip,
    layer_file,
    list_scenes,
    load_scene,
    merge_layers,
    scene_manifest,
    sync_depths,
    update_layer,
)
from contextstroke.algorithm.solve import solve

app = FastAPI(title="ContextStroke")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AddLayerRequest(BaseModel):
    name: str = "图层"
    image_base64: str
    depth: int | None = None


class MergeRequest(BaseModel):
    ids: list[str] = Field(min_length=2, max_length=2)
    depth: int | None = None

    @field_validator("depth")
    @classmethod
    def depth_is_positive(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("深度必须是正整数")
        return value


class UpdateLayerRequest(BaseModel):
    x: int | None = None
    y: int | None = None
    scale: float | None = None
    background: bool | None = None


class DepthsRequest(BaseModel):
    depths: dict[str, int] = Field(default_factory=dict)

    @field_validator("depths")
    @classmethod
    def depths_are_positive(cls, value: dict[str, int]) -> dict[str, int]:
        for name, depth in value.items():
            if depth < 1:
                raise ValueError(f"{name} 的深度必须是正整数")
        return value


class SolveRequest(BaseModel):
    scene: str
    depths: dict[str, int] | None = None
    stroke: list[list[float]] = Field(min_length=0)

    @field_validator("depths")
    @classmethod
    def depths_are_positive(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        for name, depth in value.items():
            if depth < 1:
                raise ValueError(f"{name} 的深度必须是正整数")
        return value

    @field_validator("stroke")
    @classmethod
    def stroke_points(cls, value: list[list[float]]) -> list[list[float]]:
        for point in value:
            if len(point) != 2 or not all(math.isfinite(item) for item in point):
                raise ValueError("笔触点必须是有限的二维坐标")
        return value


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/scenes")
def get_scenes() -> list[dict[str, str]]:
    return list_scenes()


@app.post("/api/scenes/import")
async def post_import(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> dict:
    payload = await file.read()
    try:
        return import_scene_zip(payload, name=name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id: str) -> dict:
    try:
        return scene_manifest(scene_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="场景清单无法读取") from error


@app.put("/api/scenes/{scene_id}/depths")
def put_depths(scene_id: str, body: DepthsRequest) -> dict:
    try:
        return sync_depths(scene_id, body.depths)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/scenes/{scene_id}/export")
def post_export(scene_id: str, body: DepthsRequest | None = None) -> FileResponse:
    try:
        zip_path, download_name = export_scene_zip(
            scene_id,
            depths=body.depths if body and body.depths else None,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    def cleanup() -> None:
        shutil.rmtree(zip_path.parent, ignore_errors=True)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=download_name,
        background=BackgroundTask(cleanup),
    )


@app.post("/api/scenes/{scene_id}/layers")
def post_layer(scene_id: str, body: AddLayerRequest) -> dict:
    try:
        png_bytes = base64.b64decode(body.image_base64, validate=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail="图片数据无法读取") from error
    try:
        return add_layer(scene_id, png_bytes, body.name, depth=body.depth)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch("/api/scenes/{scene_id}/layers/{layer_id}")
def patch_layer(scene_id: str, layer_id: str, body: UpdateLayerRequest) -> dict:
    try:
        return update_layer(
            scene_id,
            layer_id,
            x=body.x,
            y=body.y,
            scale=body.scale,
            background=body.background,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/scenes/{scene_id}/layers/{layer_id}")
def remove_layer(scene_id: str, layer_id: str) -> dict:
    try:
        return delete_layer(scene_id, layer_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/scenes/{scene_id}/layers/merge")
def post_merge(scene_id: str, body: MergeRequest) -> dict:
    try:
        return merge_layers(scene_id, body.ids[0], body.ids[1], depth=body.depth)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/scenes/{scene_id}/files/{filename}")
def get_scene_file(scene_id: str, filename: str) -> FileResponse:
    try:
        path = layer_file(scene_id, filename)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到图层文件") from error
    return FileResponse(path)


@app.post("/api/solve")
def post_solve(body: SolveRequest) -> dict:
    try:
        scene = apply_depths(load_scene(body.scene), body.depths)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="找不到场景") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return solve(scene, body.stroke)
